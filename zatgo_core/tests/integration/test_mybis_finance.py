"""MyBis finance (ERPNext's own statements, aging) and customer / supplier analytics against real documents."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import add_days, getdate, random_string, today

from zatgo_core.api.v1.mybis import finance as fin
from zatgo_core.api.v1.mybis import parties as par
from zatgo_core.tests.integration.test_mybis_analytics import _purchase, _supplier
from zatgo_core.tests.integration.test_mybis_dashboard import COMPANY, _company, _customer, _group, _invoice, _item


def _row(rows, label):
    return next(r for r in rows if r["label"] == label)


class TestMyBisFinance(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        _company()
        frappe.db.commit()

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self.cust, self.cust2 = _customer(), _customer()
        self.sup = _supplier()
        self.item = _item(_group("MyBis Cat A"))
        self.this_day = getdate(today()).replace(day=1)
        self.last_day = add_days(self.this_day, -3)
        self.inv1 = _invoice(self.cust, self.item, 2, 100, self.this_day)  # 200
        self.inv2 = _invoice(self.cust2, self.item, 1, 50, self.this_day)  # 50
        self.ret = _invoice(self.cust2, self.item, 1, 50, self.this_day, return_against=self.inv2)  # -50
        self.inv_old = _invoice(self.cust, self.item, 1, 100, self.last_day)  # 100, last month
        self.pi = _purchase(self.sup, self.item, 4, 25, self.this_day)  # 100 payable, an expense
        self.pi_old = _purchase(self.sup, self.item, 2, 25, self.last_day)  # 50 payable, last month

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _kpis(self):
        return fin.summary(company=COMPANY, preset="this_month")["data"]

    # -- headline figures ----------------------------------------------------------------------------------------------

    def test_kpis_come_from_the_ledger(self) -> None:
        k = self._kpis()
        self.assertEqual(k["revenue"]["value"], 200.0)  # 200 + 50 - 50 of sales
        self.assertEqual(k["revenue"]["previous_value"], 100.0)
        self.assertEqual(k["expenses"]["value"], 100.0)  # the purchase invoice's expense account
        self.assertEqual(k["net_profit"]["value"], 100.0)
        self.assertEqual(k["net_profit"]["margin_percent"], 50.0)
        self.assertEqual(k["receivables"]["value"], 300.0)  # all unpaid, net of the return
        self.assertEqual(k["receivables"]["previous_value"], 100.0)
        self.assertEqual(k["payables"]["value"], 150.0)
        self.assertEqual(k["payables"]["previous_value"], 50.0)
        self.assertEqual(k["cash_balance"]["value"], 0.0)
        self.assertEqual(str(k["bank_balance"]["value"]), "0.0")

    def test_trends_end_at_the_period_and_match_the_ledger(self) -> None:
        t = fin.trends(company=COMPANY, preset="this_month", months=3)["data"]
        pts = t["points"]
        self.assertEqual(len(pts), 3)
        self.assertEqual(pts[-1]["month"], str(self.this_day))
        self.assertEqual((pts[-1]["revenue"], pts[-1]["expenses"], pts[-1]["net_profit"]), (200.0, 100.0, 100.0))
        self.assertEqual((pts[-1]["receivables"], pts[-1]["payables"]), (300.0, 150.0))
        self.assertGreaterEqual(pts[-2]["receivables"], 100.0)  # last month's invoice is on the books by then (if in that month)

    # -- ERPNext statements --------------------------------------------------------------------------------------------

    def test_profit_and_loss_is_erpnexts_report_and_agrees_with_the_kpis(self) -> None:
        r = fin.profit_and_loss(company=COMPANY, preset="this_month")["data"]
        self.assertEqual(r["report"], "Profit and Loss Statement")
        income = _row(r["rows"], "Total Income (Credit)")
        self.assertEqual((income["kind"], income["value"]), ("total", 200.0))
        summary = {s["label"]: s["value"] for s in r["summary"]}
        self.assertEqual(summary["Net Profit"], self._kpis()["net_profit"]["value"])
        self.assertTrue(all("'" not in row["label"] for row in r["rows"]))  # ERPNext's display quoting is stripped
        self.assertIsNotNone(r["previous_summary"])

    def test_balance_sheet_balances_receivables_and_payables(self) -> None:
        r = fin.balance_sheet(company=COMPANY, preset="this_month")["data"]
        self.assertEqual(r["as_of"], str(getdate(today())))  # the month has not ended: a position is as of today
        summary = {s["label"]: s["value"] for s in r["summary"]}
        self.assertEqual(summary["Total Asset"], 300.0)
        self.assertEqual(summary["Total Liability"], 150.0)
        debtors = [x for x in r["rows"] if x["kind"] == "account" and x["value"] == 300.0]
        self.assertTrue(debtors)

    def test_cash_flow_returns_the_report(self) -> None:
        r = fin.cash_flow(company=COMPANY, preset="this_month")["data"]
        self.assertEqual(r["report"], "Cash Flow")
        labels = [x["label"] for x in r["rows"]]
        self.assertIn("Cash Flow from Operations", labels)
        self.assertTrue(r["summary"])

    # -- aging ---------------------------------------------------------------------------------------------------------

    def test_receivable_aging_buckets_add_up_and_drill_to_open_items(self) -> None:
        a = fin.aging(kind="receivable", company=COMPANY, preset="this_month")["data"]
        self.assertEqual(a["outstanding"], 300.0)
        self.assertAlmostEqual(sum(b["value"] for b in a["buckets"]), 300.0, places=2)
        self.assertEqual({b["key"] for b in a["buckets"]}, {"not_due", "d0_30", "d31_60", "d61_90", "d90_plus"})
        self.assertEqual([p["party"] for p in a["parties"]], [self.cust])  # cust2's invoice is cancelled out by its return
        mine = next(p for p in a["parties"] if p["party"] == self.cust)
        self.assertEqual(mine["outstanding"], 300.0)
        items = fin.party_invoices(party=self.cust, kind="receivable", company=COMPANY, preset="this_month")["data"]
        self.assertEqual({r["voucher_no"] for r in items["rows"]}, {self.inv1, self.inv_old})
        self.assertEqual(sum(r["outstanding"] for r in items["rows"]), 300.0)
        self.assertTrue(all(r["voucher_type"] == "Sales Invoice" for r in items["rows"]))

    def test_payable_aging(self) -> None:
        a = fin.aging(kind="payable", company=COMPANY, preset="this_month")["data"]
        self.assertEqual(a["outstanding"], 150.0)
        self.assertEqual(a["parties"][0]["party"], self.sup)
        items = fin.party_invoices(party=self.sup, kind="payable", company=COMPANY, preset="this_month")["data"]
        self.assertEqual({r["voucher_no"] for r in items["rows"]}, {self.pi, self.pi_old})

    def test_bad_kind_is_refused(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            fin.aging(kind="everything", company=COMPANY)
        with self.assertRaises(frappe.ValidationError):
            fin.party_invoices(party="x", kind="nope", company=COMPANY)

    # -- permissions ---------------------------------------------------------------------------------------------------

    def test_a_user_without_accounts_roles_cannot_read_statements(self) -> None:
        email = f"mybis.fin.{random_string(8).lower()}@zatgo.test"
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "F", "send_welcome_email": 0, "roles": [{"role": "Sales User"}]}).insert(ignore_permissions=True)
        frappe.clear_cache(user=email)
        frappe.set_user(email)
        for fn in (fin.profit_and_loss, fin.balance_sheet, fin.cash_flow, fin.summary):
            with self.assertRaises(frappe.PermissionError, msg=fn.__name__):
                fn(company=COMPANY)
        with self.assertRaises(frappe.PermissionError):
            fin.aging(company=COMPANY)

    # -- customers / suppliers -----------------------------------------------------------------------------------------

    def test_customer_summary_new_vs_returning_and_outstanding(self) -> None:
        s = par.summary(kind="customer", company=COMPANY, preset="this_month")["data"]
        self.assertEqual(s["active"]["value"], 2)  # cust (inv1) and cust2 (inv2)
        self.assertEqual(s["new"]["value"], 1)  # cust2 first invoiced this month; cust already had last month's
        self.assertEqual(s["returning"]["value"], 1)
        self.assertEqual(s["with_outstanding"]["value"], 1)  # cust2's return cancels its invoice
        self.assertEqual(s["total_outstanding"]["value"], 300.0)
        self.assertEqual(s["active"]["previous_value"], 1)

    def test_customer_ranking_by_revenue_and_outstanding(self) -> None:
        r = par.ranking(kind="customer", order="revenue", company=COMPANY, preset="this_month")["data"]
        top = r["rows"][0]
        self.assertEqual((top["code"], top["revenue"], top["outstanding"]), (self.cust, 200.0, 300.0))
        self.assertIn("profit", top)
        by_owed = par.ranking(kind="customer", order="outstanding", company=COMPANY, preset="this_month")["data"]
        self.assertEqual([x["code"] for x in by_owed["rows"]], [self.cust])  # cust2 owes nothing
        self.assertEqual(by_owed["rows"][0]["outstanding"], 300.0)
        orders = par.ranking(kind="customer", order="orders", company=COMPANY, preset="this_month")["data"]
        self.assertTrue(orders["rows"])

    def test_supplier_summary_and_ranking(self) -> None:
        s = par.summary(kind="supplier", company=COMPANY, preset="this_month")["data"]
        self.assertEqual((s["active"]["value"], s["new"]["value"]), (1, 0))
        self.assertEqual(s["total_outstanding"]["value"], 150.0)
        r = par.ranking(kind="supplier", order="revenue", company=COMPANY, preset="this_month")["data"]
        self.assertEqual((r["rows"][0]["code"], r["rows"][0]["revenue"], r["rows"][0]["outstanding"]), (self.sup, 100.0, 150.0))
        self.assertNotIn("profit", r["rows"][0])
        with self.assertRaises(frappe.ValidationError):
            par.ranking(kind="supplier", order="profit", company=COMPANY)  # purchases have no profit
        with self.assertRaises(frappe.ValidationError):
            par.summary(kind="employee", company=COMPANY)
