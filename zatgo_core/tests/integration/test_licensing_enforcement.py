"""Licence enforcement on a real site: what a Sales-only licence lets through, refuses, and never touches.

Money path included: a licensed Sales Invoice still submits and posts its GL Entries; an unlicensed Stock Entry
is refused before anything reaches the stock ledger; a document made before the licence can still be read,
printed and cancelled (its ledger reversed), but not amended.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import nowdate, random_string

from zatgo_core.licensing import desk, edition_config, entitlement, gate
from zatgo_core.licensing.entitlement import Entitlement
from zatgo_core.services import app_authority, app_state, vansalex_access
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


@contextmanager
def licensed(features, switch: bool = True):
    """Enforce an entitlement for the block (the switch lives in site_config in real life)."""
    before = frappe.local.conf.get(entitlement.CONF_KEY)
    if switch:
        frappe.local.conf[entitlement.CONF_KEY] = 1
    entitlement.use(Entitlement.from_features(features, source="test"))
    try:
        yield
    finally:
        entitlement.use(None)
        if before is None:
            frappe.local.conf.pop(entitlement.CONF_KEY, None)
        else:
            frappe.local.conf[entitlement.CONF_KEY] = before


SALES = edition_config.get_preset("sales")["features"]
DISTRIBUTION = edition_config.get_preset("distribution")["features"]


class TestLicensingEnforcement(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.company = get_or_create_test_company()
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        cls.warehouse = f"LicenceTest - {abbr}"
        if not frappe.db.exists("Warehouse", cls.warehouse):
            frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "LicenceTest", "company": cls.company}).insert(
                ignore_permissions=True)
        group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        cls.stock_item = f"LIC-STOCK-{random_string(6).upper()}"
        cls.service_item = f"LIC-SERVICE-{random_string(6).upper()}"
        for code, is_stock in ((cls.stock_item, 1), (cls.service_item, 0)):
            frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": group,
                            "stock_uom": "Nos", "is_stock_item": is_stock}).insert(ignore_permissions=True)
        cls.customer = "Licence Test Customer"
        if not frappe.db.exists("Customer", cls.customer):
            frappe.get_doc({"doctype": "Customer", "customer_name": cls.customer, "customer_type": "Individual",
                            "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                            "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name")}).insert(
                ignore_permissions=True)
        cls.user = f"zg-lic-enf-{random_string(6).lower()}@example.com"
        frappe.get_doc({"doctype": "User", "email": cls.user, "first_name": "Licence", "send_welcome_email": 0,
                        "roles": [{"role": r} for r in ("System Manager", "Accounts Manager", "Stock Manager",
                                                        "Sales Manager", "Purchase Manager")]}).insert(
            ignore_permissions=True)

    def tearDown(self) -> None:
        frappe.flags.pop("zg_licence_cascade", None)
        entitlement.use(None)
        frappe.local.conf.pop(entitlement.CONF_KEY, None)
        frappe.set_user("Administrator")

    # -- builders -----------------------------------------------------------------------------------------------

    def _invoice(self, **extra):
        return frappe.get_doc({
            "doctype": "Sales Invoice", "customer": self.customer, "company": self.company, "currency": "SAR",
            "conversion_rate": 1, "due_date": nowdate(),
            "items": [{"item_code": self.service_item, "qty": 1, "rate": 100}], **extra,
        })

    def _receipt(self):
        return frappe.get_doc({
            "doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": self.company,
            "items": [{"item_code": self.stock_item, "qty": 5, "t_warehouse": self.warehouse, "basic_rate": 10}],
        })

    # -- off unless switched on and licensed --------------------------------------------------------------------

    def test_this_site_is_unrestricted_by_default(self) -> None:
        self.assertIsNone(entitlement.active())
        self.assertFalse(entitlement.describe()["enforcing"])

    def test_an_entitlement_without_the_switch_changes_nothing(self) -> None:
        frappe.set_user(self.user)
        with licensed(SALES, switch=False):
            self._receipt().insert(ignore_permissions=True).submit()

    # -- the money path ---------------------------------------------------------------------------------------

    def test_a_licensed_invoice_submits_and_posts_its_ledger(self) -> None:
        frappe.set_user(self.user)
        with licensed(SALES):
            si = self._invoice().insert(ignore_permissions=True)
            si.submit()
        rows = frappe.get_all("GL Entry", filters={"voucher_no": si.name, "is_cancelled": 0},
                              fields=["debit", "credit"])
        self.assertTrue(rows)
        self.assertGreater(sum(r.debit for r in rows), 0)
        self.assertEqual(sum(r.debit for r in rows), sum(r.credit for r in rows))

    def test_an_unlicensed_stock_entry_never_reaches_the_ledger(self) -> None:
        frappe.set_user(self.user)
        before = frappe.db.count("Stock Ledger Entry", {"item_code": self.stock_item})
        with licensed(SALES):
            with self.assertRaises(frappe.PermissionError) as ctx:
                self._receipt().insert(ignore_permissions=True)
        self.assertIn("Material Receipt", str(ctx.exception))
        self.assertEqual(frappe.db.count("Stock Ledger Entry", {"item_code": self.stock_item}), before)

    def test_purchasing_is_refused_on_a_sales_licence(self) -> None:
        frappe.set_user(self.user)
        supplier = frappe.db.get_value("Supplier", {}, "name")
        if not supplier:
            self.skipTest("no Supplier on this site")
        with licensed(SALES), self.assertRaises(frappe.PermissionError):
            # With permission checks on: refused by the has_permission layer before the controller runs.
            frappe.get_doc({"doctype": "Purchase Invoice", "supplier": supplier, "company": self.company,
                            "items": [{"item_code": self.service_item, "qty": 1, "rate": 5}]}).insert()

    def test_a_return_needs_the_return_feature(self) -> None:
        frappe.set_user(self.user)
        with licensed({"sales.invoice": []}):
            si = self._invoice().insert(ignore_permissions=True)
            si.submit()
            from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

            ret = make_sales_return(si.name)
            with self.assertRaises(frappe.PermissionError):
                ret.insert(ignore_permissions=True)
        with licensed({"sales.invoice": [], "sales.return": []}):
            ret = make_sales_return(si.name)
            ret.insert(ignore_permissions=True)
            ret.submit()
        self.assertTrue(frappe.db.exists("GL Entry", {"voucher_no": ret.name, "is_cancelled": 0}))

    def test_narrowed_actions_stop_at_submit(self) -> None:
        frappe.set_user(self.user)
        with licensed({"sales.invoice": ["read", "create", "write"]}):
            si = self._invoice().insert(ignore_permissions=True)
            with self.assertRaises(frappe.PermissionError):
                si.submit()
        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "docstatus"), 0)

    # -- history stays: read, print, cancel; no amend ---------------------------------------------------------

    def test_existing_records_stay_readable_and_cancellable_but_not_amendable(self) -> None:
        se = self._receipt().insert(ignore_permissions=True)
        se.submit()  # made before the licence, as Administrator
        frappe.set_user(self.user)
        with licensed(SALES):
            for ptype in ("read", "print", "email", "export", "cancel"):
                self.assertTrue(frappe.has_permission("Stock Entry", ptype, doc=se, user=self.user), ptype)
            self.assertFalse(frappe.has_permission("Stock Entry", "write", doc=frappe.get_doc("Stock Entry", se.name),
                                                   user=self.user))
            doc = frappe.get_doc("Stock Entry", se.name)
            doc.cancel()
            self.assertEqual(frappe.db.get_value("Stock Entry", se.name, "docstatus"), 2)
            self.assertEqual(frappe.db.count("Stock Ledger Entry", {"voucher_no": se.name, "is_cancelled": 0}), 0)
            amended = frappe.copy_doc(doc)
            amended.amended_from = doc.name
            amended.docstatus = 0
            with self.assertRaises(frappe.PermissionError):
                amended.insert(ignore_permissions=True)

    def test_permission_layer_answers_per_doctype(self) -> None:
        """The licence only ever takes away writes. Compared with the same check made without a licence, because
        this site's own role permissions decide the baseline."""
        unlicensed = ["Warehouse", "Item", "Purchase Order", "Supplier", "Material Request", "Journal Entry"]
        licensed_dts = ["Customer", "Quotation", "Sales Order", "Pricing Rule"]

        def check(doctype, ptype):
            return frappe.has_permission(doctype, ptype, doc=frappe.get_doc({"doctype": doctype}), user=self.user)

        base = {(dt, p): check(dt, p) for dt in unlicensed + licensed_dts + ["ToDo"] for p in ("read", "write")}
        with licensed(SALES):
            now = {(dt, p): check(dt, p) for dt, p in base}
        writable = [dt for dt in unlicensed if base[(dt, "write")]]
        self.assertTrue(writable, "the test user needs write on some unlicensed DocType to test anything")
        for dt in writable:
            self.assertFalse(now[(dt, "write")], f"{dt}: write should be taken by a Sales licence")
        for dt in unlicensed + licensed_dts + ["ToDo"]:
            self.assertEqual(now[(dt, "read")], base[(dt, "read")], f"{dt}: reading is never taken")
        for dt in licensed_dts + ["ToDo"]:
            self.assertEqual(now[(dt, "write")], base[(dt, "write")], f"{dt}: licensed / not product-controlled")

    def test_submit_and_cancel_pass_through_the_write_check(self) -> None:
        frappe.set_user(self.user)
        with licensed({"sales.invoice": ["read", "create", "submit"]}):  # no "write"
            si = self._invoice().insert(ignore_permissions=True)
            si.submit()
            self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "docstatus"), 1)
            si.reload()
            si.cancel()
            self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "docstatus"), 2)

    def test_administrator_is_enforced_in_a_request_not_in_system_jobs(self) -> None:
        with licensed(SALES):
            self._receipt().insert(ignore_permissions=True)  # no request: scheduler / console
            frappe.local.request = SimpleNamespace(path="/api/resource/Stock Entry", method="POST", headers={})
            try:
                with self.assertRaises(frappe.PermissionError):
                    self._receipt().insert(ignore_permissions=True)
            finally:
                frappe.local.request = None

    # -- apps, industries, VanSaleX ---------------------------------------------------------------------------

    def test_apps_and_keys_follow_the_licence(self) -> None:
        with licensed(SALES):
            self.assertFalse(app_state.is_on("vansalex"))
            self.assertFalse(app_state.switches().get("vansalex"))
            self.assertFalse(gate.industry_licensed("gym"))
            self.assertFalse(vansalex_access.effective("Administrator")["modules"]["sales_invoice"])
            self.assertTrue(gate.app_licensed("core_settings"))  # not a licensed product: untouched
        with licensed(DISTRIBUTION):
            self.assertEqual(app_state.is_on("vansalex"), app_state.switches().get("vansalex"))
            self.assertTrue(gate.vansalex_key_licensed("inventory.transfer"))

    def test_switching_on_an_unlicensed_app_is_refused(self) -> None:
        settings = frappe.get_doc("ZatGo System Settings")
        before = frappe.get_doc(settings.as_dict())
        before.enable_mybis = 0
        after = frappe.get_doc(settings.as_dict())
        after.enable_mybis = 1
        with licensed(SALES), self.assertRaises(frappe.PermissionError):
            app_authority.assert_can_switch(before, after)
        with licensed({**{f: [] for f in SALES}, "zatgo_apps.mybis": []}):
            app_authority.assert_can_switch(before, after)
        app_authority.assert_can_switch(before, after)  # unenforced: as before

    # -- Desk --------------------------------------------------------------------------------------------------

    def test_desk_entries_of_unlicensed_features_are_left_out(self) -> None:
        def boot():
            return frappe._dict(
                workspaces={"pages": [{"name": n} for n in ("Stock", "Selling", "Invoicing", "My Own")]},
                workspace_sidebar_item={"stock": {"items": [1]}, "selling": {"items": [1]}},
                desktop_icons=[{"label": "Stock"}, {"label": "Selling"}, {"label": "My Own"}],
                page_info={"stock-balance": {}, "permission-manager": {}},
            )

        untouched = boot()
        desk.filter_boot(untouched)
        self.assertEqual(len(untouched.workspaces["pages"]), 4)
        with licensed(SALES):
            b = boot()
            desk.filter_boot(b)
        self.assertEqual([p["name"] for p in b.workspaces["pages"]], ["Selling", "Invoicing", "My Own"])
        self.assertEqual(list(b.workspace_sidebar_item), ["selling"])
        self.assertEqual([i["label"] for i in b.desktop_icons], ["Selling", "My Own"])
        self.assertEqual(list(b.page_info), ["permission-manager"])
        self.assertIn("Stock", b.zatgo_licence["hidden_workspaces"])

    # -- records ERPNext creates inside another record's own save ---------------------------------------------

    def test_creating_a_company_still_creates_its_chart_and_warehouses(self) -> None:
        """Company.on_update creates Accounts, Warehouses, Cost Centers, Departments and tax templates. The
        licence allows creating a Company (foundation.setup), so it must allow what that creation does."""
        frappe.set_user(self.user)
        name = f"Licence Cascade {random_string(5)}"
        with licensed(SALES):
            company = frappe.get_doc({"doctype": "Company", "company_name": name, "abbr": random_string(4).upper(),
                                      "default_currency": "SAR", "country": "Saudi Arabia"}).insert(
                ignore_permissions=True)
            for doctype in ("Account", "Warehouse", "Cost Center"):
                self.assertTrue(frappe.db.exists(doctype, {"company": company.name}), doctype)
            # ...and the cascade is over: the same request cannot create unlicensed documents afterwards.
            with self.assertRaises(frappe.PermissionError):
                self._receipt().insert(ignore_permissions=True)
