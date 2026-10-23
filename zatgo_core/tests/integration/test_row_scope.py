"""API reads respect User Permissions (services/row_scope.py): a user restricted to one Company never sees another
company's rows through the shared lists, the accounting dashboard and the SQL-based ledger reports, and a portal
(Website User) session only ever sees its own party's orders.

Runs against a real site; creates a second Company and throwaway users (left on the test site, like the other suites)."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1.accounting import dashboard, reports
from zatgo_core.services import erpnext_reads, row_scope
from zatgo_core.tests.integration._fixtures import get_or_create_test_company

OTHER_COMPANY = "ZatGo Scope Test Co"


def _other_company() -> str:
	if not frappe.db.exists("Company", OTHER_COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": OTHER_COMPANY,
				"abbr": "ZSTC",
				"default_currency": "SAR",
				"country": "Saudi Arabia",
			}
		).insert(ignore_permissions=True)
	return OTHER_COMPANY


def _user(*roles: str, user_type: str = "System User") -> str:
	email = f"scope.{random_string(8).lower()}@zatgo.test"
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Scope",
			"send_welcome_email": 0,
			"user_type": user_type,
			"roles": [{"role": r} for r in roles],
		}
	).insert(ignore_permissions=True)
	return email


def _restrict_to_company(user: str, company: str) -> None:
	frappe.get_doc({"doctype": "User Permission", "user": user, "allow": "Company", "for_value": company}).insert(
		ignore_permissions=True
	)
	frappe.clear_cache(user=user)


class TestRowScope(IntegrationTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		cls.company_a = get_or_create_test_company()
		cls.company_b = _other_company()
		# VanSale Admin as well: on a site that ran ensure_vansale_perms, Warehouse / Account / Sales Invoice /
		# Sales Order / Bin carry Custom DocPerm rows for the VanSale roles only (the standard roles' rows are
		# replaced wholesale), so the accounting roles alone cannot read them there.
		roles = ("Accounts User", "Accounts Manager", "Stock User", "VanSale Admin")
		cls.restricted = _user(*roles)
		_restrict_to_company(cls.restricted, cls.company_b)
		cls.free = _user(*roles)  # no Company User Permission

	def tearDown(self) -> None:
		frappe.set_user("Administrator")

	# -- the helpers -------------------------------------------------------------

	def test_the_company_restriction_comes_from_user_permissions(self) -> None:
		self.assertIsNone(row_scope.permitted_companies("Administrator"))
		self.assertIsNone(row_scope.permitted_companies(self.free))
		self.assertEqual(row_scope.permitted_companies(self.restricted), [self.company_b])
		frappe.set_user(self.restricted)
		params: dict = {}
		self.assertEqual(row_scope.company_clause("gle.company", params), " AND gle.company IN %(zg_companies)s")
		self.assertEqual(params["zg_companies"], (self.company_b,))
		frappe.set_user(self.free)
		self.assertEqual(row_scope.company_clause("gle.company", {}), "")

	def test_naming_a_company_you_may_not_read_is_refused(self) -> None:
		frappe.set_user(self.restricted)
		row_scope.require_company(self.company_b)
		row_scope.require_company(None)
		with self.assertRaises(frappe.PermissionError):
			row_scope.require_company(self.company_a)

	def test_count_follows_permissions(self) -> None:
		frappe.set_user("Administrator")
		everything = row_scope.count("Warehouse")
		self.assertGreater(everything, 0, "the test company has warehouses")
		frappe.set_user(self.restricted)
		# restricted to company B: company A's warehouses are not counted ...
		self.assertLess(row_scope.count("Warehouse"), everything)
		# ... and asking for company A by name finds nothing
		self.assertEqual(row_scope.count("Warehouse", {"company": self.company_a}), 0)

	# -- the shared list helpers ---------------------------------------------------

	def test_the_shared_lists_hide_other_companies(self) -> None:
		frappe.set_user("Administrator")
		admin_rows = erpnext_reads.list_warehouses(page_size=100)["data"]
		self.assertTrue(any(r["company"] == self.company_a for r in admin_rows))
		frappe.set_user(self.restricted)
		rows = erpnext_reads.list_warehouses(page_size=100)["data"]
		self.assertFalse([r for r in rows if r["company"] == self.company_a], "company A's warehouses leaked")
		frappe.set_user(self.free)
		free_rows = erpnext_reads.list_warehouses(page_size=100)["data"]
		self.assertEqual(len(free_rows), len(admin_rows), "an unrestricted user sees what they always saw")

	def test_the_chart_of_accounts_follows_the_company_restriction(self) -> None:
		frappe.set_user(self.restricted)
		self.assertEqual(erpnext_reads.list_accounts(company=self.company_a)["data"], [])
		self.assertTrue(erpnext_reads.list_accounts(company=self.company_b)["data"], "their own company's chart is there")

	# -- accounting dashboard and ledger reports -----------------------------------

	def test_the_dashboard_totals_only_the_users_companies(self) -> None:
		frappe.set_user(self.restricted)
		data = dashboard.summary()["data"]
		self.assertEqual(data["sales_invoice_count"], row_scope.count("Sales Invoice"))
		# company B has no invoices: nothing of company A's may appear in any figure
		self.assertEqual((data["ar_open"], data["ap_open"], data["ar_overdue"], data["ap_overdue"]), (0, 0, 0, 0))
		self.assertEqual((data["open_receivables"], data["open_payables"], data["recent_sales_invoices"]), ([], [], []))

	def test_the_dashboard_for_an_unrestricted_user_is_unchanged(self) -> None:
		frappe.set_user("Administrator")
		admin = dashboard.summary()["data"]
		frappe.set_user(self.free)
		free = dashboard.summary()["data"]
		self.assertEqual(
			(free["ar_open"], free["ap_open"], free["sales_invoice_count"], free["purchase_invoice_count"]),
			(admin["ar_open"], admin["ap_open"], admin["sales_invoice_count"], admin["purchase_invoice_count"]),
		)

	def test_trial_balance_and_profit_and_loss_are_company_scoped(self) -> None:
		frappe.set_user(self.restricted)
		tb = reports.trial_balance()["data"]
		self.assertFalse([r for r in tb if r["account"].endswith(" - ZCTC")], "company A accounts in a company-B user's trial balance")
		pl = reports.profit_and_loss()["data"]
		self.assertEqual((pl["income"], pl["expense"]), ([], []))
		with self.assertRaises(frappe.PermissionError):
			reports.trial_balance(company=self.company_a)
		with self.assertRaises(frappe.PermissionError):
			reports.profit_and_loss(company=self.company_a)

	def test_profit_and_loss_takes_a_company(self) -> None:
		frappe.set_user("Administrator")
		pl_a = reports.profit_and_loss(company=self.company_a)
		pl_b = reports.profit_and_loss(company=self.company_b)
		self.assertTrue(pl_a["success"] and pl_b["success"])
		for line in pl_b["data"]["income"] + pl_b["data"]["expense"]:
			self.assertTrue(line["account"].endswith(" - ZSTC"), line)

	def test_the_ledger_openings_are_company_scoped(self) -> None:
		# An account of company A, asked for by a company-B user: no opening balance, no rows.
		account = frappe.db.get_value("Account", {"company": self.company_a, "is_group": 0}, "name")
		self.assertTrue(account, "the test company has a leaf account")
		frappe.set_user(self.restricted)
		out = reports.account_ledger(account=account)
		self.assertEqual((out["data"], out["meta"]["opening_balance"], out["meta"]["closing_balance"]), ([], 0, 0))

	# -- portals -------------------------------------------------------------------

	def test_a_portal_session_only_gets_its_own_partys_orders(self) -> None:
		with patch.object(row_scope, "portal_parties", return_value=["C1"]), patch.object(
			erpnext_reads.frappe, "get_list", return_value=[]
		) as get_list, patch.object(row_scope, "count", return_value=0):
			erpnext_reads.list_sales_orders()
		self.assertEqual(get_list.call_args.kwargs["filters"]["customer"], ["in", ["C1"]])
		with patch.object(row_scope, "portal_parties", return_value=[]), patch.object(erpnext_reads.frappe, "get_list") as get_list:
			out = erpnext_reads.list_purchase_orders()
		get_list.assert_not_called()
		self.assertEqual(out["data"], [])

	def test_a_portal_session_cannot_open_someone_elses_order(self) -> None:
		order = frappe._dict(doctype="Sales Order", name="SO-X", customer="C2", customer_name="C2", status="Draft", grand_total=1, transaction_date=None)
		with patch.object(row_scope, "portal_parties", return_value=["C1"]), patch.object(
			erpnext_reads.frappe, "get_doc", return_value=order
		), patch.object(erpnext_reads.frappe.db, "exists", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				erpnext_reads.get_sales_order("SO-X")

	def test_a_website_user_resolves_to_its_own_parties_not_everyones(self) -> None:
		portal = _user("Customer", user_type="Website User")
		frappe.set_user(portal)
		self.assertEqual(row_scope.portal_parties("Sales Order", "customer"), [])
		frappe.set_user("Administrator")
		self.assertIsNone(row_scope.portal_parties("Sales Order", "customer"))


STAFF_ONLY = (
	"ZG Delivery Boy",
	"ZG Delivery Stop",
	"ZG Vehicle",
	"ZG Service Ticket",
	"ZG Order",
	"ZG Table",
	"ZG KDS Ticket",
)


class TestStaffOnlyDocTypes(IntegrationTestCase):
	"""The delivery / fleet / service / restaurant DocTypes were readable and writable by the role "All" -- every
	logged-in user, a self-registered portal user included. They are staff DocTypes: "Desk User" (every System
	User, nobody else)."""

	def tearDown(self) -> None:
		frappe.set_user("Administrator")

	def test_no_staff_doctype_grants_the_all_role(self) -> None:
		"""What the package ships: the DocType JSON (a site's Custom DocPerm rows, seeded by ensure_vansale_perms
		for some of these, replace it wholesale -- that is a separate mechanism)."""
		import json
		import os

		base = frappe.get_app_path("zatgo_core", "zatgo_core", "doctype")
		for dt in STAFF_ONLY:
			slug = frappe.scrub(dt)
			with open(os.path.join(base, slug, f"{slug}.json"), encoding="utf-8") as f:
				roles = {p["role"] for p in json.load(f)["permissions"]}
			self.assertNotIn("All", roles, dt)
			self.assertIn("Desk User", roles, dt)

	def test_a_portal_user_is_out_and_a_system_user_is_unchanged(self) -> None:
		portal = _user("Customer", user_type="Website User")
		staff = _user("Sales User")
		for dt in STAFF_ONLY:
			self.assertFalse(frappe.has_permission(dt, "read", user=portal), f"{dt}: portal user can read")
			self.assertFalse(frappe.has_permission(dt, "create", user=portal), f"{dt}: portal user can create")
			if frappe.db.exists("Custom DocPerm", {"parent": dt}):
				continue  # this site's Custom DocPerm rows (VanSale roles) replace the shipped ones
			self.assertTrue(frappe.has_permission(dt, "read", user=staff), f"{dt}: staff lost access")
			self.assertTrue(frappe.has_permission(dt, "create", user=staff), f"{dt}: staff lost access")
