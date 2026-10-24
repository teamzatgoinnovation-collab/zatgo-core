"""MyBis dashboard figures against real ERPNext documents: invoices, returns, the ledger and the ranking queries are checked
against hand-computed expectations. A throwaway company keeps other suites' invoices out of the totals; every test rolls back."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import add_months, getdate, random_string, today

from zatgo_core.api.v1.mybis import dashboard as api
from zatgo_core.tests.integration._fixtures import get_or_create_test_company

COMPANY = "ZatGo MyBis KPI Co"


def _company() -> str:
    if not frappe.db.exists("Company", COMPANY):
        frappe.get_doc(
            {"doctype": "Company", "company_name": COMPANY, "abbr": "ZMK", "default_currency": "SAR", "country": "Saudi Arabia"}
        ).insert(ignore_permissions=True)
    return COMPANY


def _group(name: str) -> str:
    if not frappe.db.exists("Item Group", name):
        frappe.get_doc({"doctype": "Item Group", "item_group_name": name, "parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)
    return name


def _item(group: str) -> str:
    code = f"MYBIS-{random_string(6).upper()}"
    frappe.get_doc(
        {"doctype": "Item", "item_code": code, "item_name": code, "item_group": group, "stock_uom": "Nos", "is_stock_item": 0}
    ).insert(ignore_permissions=True)
    return code


def _customer() -> str:
    doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": f"MyBis Cust {random_string(6)}",
            "customer_type": "Individual",
            "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
            "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _invoice(customer: str, item: str, qty: float, rate: float, posting_date, *, return_against: str | None = None) -> str:
    doc = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "company": COMPANY,
            "customer": customer,
            "posting_date": posting_date,
            "set_posting_time": 1,
            "due_date": posting_date,
            "update_stock": 0,
            "is_return": 1 if return_against else 0,
            "return_against": return_against,
            "items": [{"item_code": item, "qty": -abs(qty) if return_against else qty, "rate": rate}],
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


class TestMyBisDashboard(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        _company()
        frappe.db.commit()

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self.cust = _customer()
        self.cat_a, self.cat_b = _group("MyBis Cat A"), _group("MyBis Cat B")
        self.item_a, self.item_b = _item(self.cat_a), _item(self.cat_b)
        now = getdate(today())
        self.this_day = now.replace(day=1)
        self.last_day = add_months(self.this_day, -1)
        # this month: A 2 x 100 = 200, B 1 x 50 = 50, return of 1 x 50 from B; last month: A 1 x 100
        self.inv_a = _invoice(self.cust, self.item_a, 2, 100, self.this_day)
        self.inv_b = _invoice(self.cust, self.item_b, 1, 50, self.this_day)
        self.ret = _invoice(self.cust, self.item_b, 1, 50, self.this_day, return_against=self.inv_b)
        _invoice(self.cust, self.item_a, 1, 100, self.last_day)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _kpis(self, **kw):
        return api.kpis(company=COMPANY, preset="this_month", **kw)["data"]

    def test_sales_figures_match_the_documents(self) -> None:
        k = self._kpis()
        self.assertEqual(k["currency"], "SAR")
        self.assertEqual(k["total_sales"]["value"], 250.0)  # returns are not "sales"
        self.assertEqual(k["total_sales"]["previous_value"], 100.0)
        self.assertEqual(k["total_sales"]["growth_percent"], 150.0)
        self.assertEqual(k["net_sales"]["value"], 200.0)  # 250 - 50 returned
        self.assertEqual(k["sales_detail"]["returns"]["value"], -50.0)
        self.assertEqual(k["sales_detail"]["invoices"]["value"], 2)

    def test_gross_profit_and_net_profit_come_from_the_ledger(self) -> None:
        k = self._kpis()
        gl_income = frappe.db.sql(
            """SELECT COALESCE(SUM(gle.credit - gle.debit), 0) FROM `tabGL Entry` gle JOIN `tabAccount` a ON a.name = gle.account
               WHERE gle.company = %s AND a.root_type = 'Income' AND gle.is_cancelled = 0 AND gle.posting_date >= %s""",
            (COMPANY, self.this_day),
        )[0][0]
        self.assertEqual(k["net_profit"]["value"], float(gl_income))  # no expenses were posted
        self.assertEqual(k["gross_profit"]["value"], 200.0)  # non-stock items: no COGS
        self.assertEqual(k["gross_profit"]["margin_percent"], 100.0)
        self.assertIn(k["gross_profit"]["basis"], ("gl", "valuation_estimate"))
        self.assertEqual(k["expenses"]["value"], 0.0)

    def test_receivables_are_the_ledger_balance_as_of_each_period_end(self) -> None:
        k = self._kpis()
        recv = frappe.db.sql(
            """SELECT COALESCE(SUM(gle.debit - gle.credit), 0) FROM `tabGL Entry` gle JOIN `tabAccount` a ON a.name = gle.account
               WHERE gle.company = %s AND a.account_type = 'Receivable' AND gle.is_cancelled = 0""",
            (COMPANY,),
        )[0][0]
        self.assertEqual(k["receivables"]["value"], float(recv))
        self.assertEqual(k["receivables"]["previous_value"], 100.0)  # only last month's invoice existed at its end

    def test_compare_off_has_no_previous_values(self) -> None:
        k = self._kpis(compare=0)
        self.assertIsNone(k["total_sales"]["previous_value"])
        self.assertIsNone(k["total_sales"]["growth_percent"])

    def test_sales_trend_sums_to_net_sales_and_fills_gaps(self) -> None:
        t = api.sales_trend(company=COMPANY, preset="this_month")["data"]
        self.assertEqual(t["group_by"], "day")
        self.assertAlmostEqual(sum(p["value"] for p in t["current"]), 200.0)
        self.assertEqual(sum(p["value"] for p in t["previous"]), 100.0)
        self.assertGreaterEqual(len(t["current"]), 28)
        with self.assertRaises(frappe.ValidationError):
            api.sales_trend(company=COMPANY, group_by="hour")

    def test_top_categories_net_off_returns_with_share_and_growth(self) -> None:
        r = api.top_categories(company=COMPANY, preset="this_month")["data"]
        rows = {x["code"]: x for x in r["rows"]}
        self.assertEqual(rows[self.cat_a]["revenue"], 200.0)
        self.assertNotIn(self.cat_b, rows)  # 50 sold - 50 returned = nothing net: not a top category
        self.assertEqual(rows[self.cat_a]["share_percent"], 100.0)
        self.assertEqual(rows[self.cat_a]["previous_revenue"], 100.0)
        self.assertEqual(rows[self.cat_a]["growth_percent"], 100.0)

    def test_top_products(self) -> None:
        r = api.top_products(company=COMPANY, preset="this_month", limit=1)["data"]
        self.assertEqual(len(r["rows"]), 1)
        self.assertEqual(r["rows"][0]["code"], self.item_a)
        self.assertEqual(r["rows"][0]["quantity"], 2.0)
        with self.assertRaises(frappe.ValidationError):
            api.top_products(company=COMPANY, order="profit")

    def test_response_is_cached_with_its_age_and_refresh_recomputes(self) -> None:
        first = api.kpis(company=COMPANY, preset="this_month", refresh=1)
        second = api.kpis(company=COMPANY, preset="this_month")
        self.assertFalse(first["meta"]["cached"])
        self.assertTrue(second["meta"]["cached"])
        self.assertEqual(first["meta"]["cached_at"], second["meta"]["cached_at"])
        self.assertEqual(second["meta"]["company"], COMPANY)

    def test_other_company_is_refused_for_a_restricted_user(self) -> None:
        mine = get_or_create_test_company()
        email = f"mybis.kpi.{random_string(8).lower()}@zatgo.test"
        frappe.get_doc(
            {"doctype": "User", "email": email, "first_name": "K", "send_welcome_email": 0, "roles": [{"role": "System Manager"}, {"role": "Accounts Manager"}]}
        ).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Company", "for_value": mine}).insert(ignore_permissions=True)
        frappe.clear_cache(user=email)
        frappe.set_user(email)
        with self.assertRaises(frappe.PermissionError):
            api.kpis(company=COMPANY)

    def test_record_level_restrictions_other_than_company_are_refused(self) -> None:
        email = f"mybis.kpi2.{random_string(8).lower()}@zatgo.test"
        frappe.get_doc(
            {"doctype": "User", "email": email, "first_name": "K", "send_welcome_email": 0, "roles": [{"role": "System Manager"}, {"role": "Accounts Manager"}]}
        ).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Customer", "for_value": self.cust}).insert(ignore_permissions=True)
        frappe.clear_cache(user=email)
        frappe.set_user(email)
        with self.assertRaises(frappe.PermissionError):
            api.kpis(company=COMPANY)

    def test_a_user_without_ledger_access_gets_unavailable_not_zero(self) -> None:
        email = f"mybis.kpi3.{random_string(8).lower()}@zatgo.test"
        frappe.get_doc(
            {"doctype": "User", "email": email, "first_name": "K", "send_welcome_email": 0, "roles": [{"role": "Sales User"}]}
        ).insert(ignore_permissions=True)
        frappe.clear_cache(user=email)
        frappe.set_user(email)
        if frappe.has_permission("GL Entry", "read"):
            self.skipTest("Sales User can read GL Entry on this site")
        k = api.kpis(company=COMPANY)["data"]
        self.assertFalse(k["net_profit"]["available"])
        self.assertFalse(k["receivables"]["available"])
