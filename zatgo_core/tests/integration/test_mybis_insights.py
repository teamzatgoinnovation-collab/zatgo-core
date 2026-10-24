"""MyBis insights / alerts and forecast endpoints against real documents. Every rule is checked from the documents that trigger it."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import add_days, add_months, getdate, random_string, today

from zatgo_core.api.v1.mybis import alerts as alerts_api
from zatgo_core.api.v1.mybis import forecast as fc_api
from zatgo_core.services.mybis import insights
from zatgo_core.services.mybis import period as periods
from zatgo_core.services.mybis.scope import Scope
from zatgo_core.tests.integration.test_mybis_analytics import _expense_account, _purchase, _supplier
from zatgo_core.tests.integration.test_mybis_dashboard import COMPANY, _company, _customer, _group, _invoice, _item

DRILL_SCREENS = {"dashboard", "sales", "purchases", "inventory", "customers", "suppliers", "finance"}


def _ids(data):
    return {i["id"]: i for i in data["items"]}


def _month_start(d):
    return getdate(d).replace(day=1)


class TestMyBisInsights(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        _company()
        frappe.db.commit()

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self.this_first = _month_start(today())
        self.prev_first = _month_start(add_months(self.this_first, -1))
        self.cat_a, self.cat_b = _group("MyBis Cat A"), _group("MyBis Cat B")
        self.item_a, self.item_b = _item(self.cat_a), _item(self.cat_b)
        self.c1, self.c2 = _customer(), _customer()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def feed(self, **kw):
        return alerts_api.feed(company=COMPANY, preset=kw.pop("preset", "this_month"), refresh=1, **kw)["data"]

    # -- sales decline: critical, with its working shown ----------------------------------------------------------------

    def test_a_sales_collapse_raises_linked_alerts_with_their_calculation(self) -> None:
        _invoice(self.c1, self.item_a, 10, 100, self.prev_first)  # 1000 in the comparable window of the previous month
        _invoice(self.c1, self.item_a, 1, 100, self.this_first)  # 100 this month
        d = self.feed()
        items = _ids(d)
        decline = items["sales_decline"]
        self.assertEqual((decline["type"], decline["severity"], decline["category"]), ("alert", "critical", "sales"))
        self.assertEqual((decline["current_value"], decline["previous_value"], decline["change_percent"]), (100.0, 1000.0, -90.0))
        self.assertIn("previous period", decline["calculation"])
        self.assertEqual(decline["data"][0]["value"], 100.0)
        self.assertEqual(decline["drill"]["screen"], "sales")
        self.assertEqual(items["profit_decline"]["severity"], "medium")  # profit fell 90% but stayed positive
        self.assertEqual(items[f"category_decline:{self.cat_a}"]["severity"], "high")
        self.assertEqual(items[f"category_decline:{self.cat_a}"]["drill"]["filters"], {"category": self.cat_a})
        self.assertIn("top_customer", items)
        self.assertEqual(items["top_customer"]["drill"]["filters"], {"customer": self.c1})
        overdue = items["receivables_overdue"]
        self.assertEqual(overdue["current_value"], 1100.0)  # both invoices were due on their posting dates
        self.assertEqual(items[f"customer_overdue:{self.c1}"]["drill"], {"screen": "finance", "tab": "receivable", "party": self.c1})
        self.assertNotIn("sales_growth", items)

    def test_sorting_structure_and_fingerprints(self) -> None:
        _invoice(self.c1, self.item_a, 10, 100, self.prev_first)
        _invoice(self.c1, self.item_a, 1, 100, self.this_first)
        a, b = self.feed(), self.feed()
        rank = [insights.RANK[i["severity"]] for i in a["items"]]
        self.assertEqual(rank, sorted(rank))
        self.assertEqual([i["fingerprint"] for i in a["items"]], [i["fingerprint"] for i in b["items"]])
        self.assertEqual(sum(a["counts"]["by_severity"].values()), len(a["items"]))
        self.assertEqual(a["counts"]["alerts"] + a["counts"]["insights"], len(a["items"]))
        for i in a["items"]:
            self.assertIn(i["type"], ("alert", "insight"))
            self.assertIn(i["severity"], insights.SEVERITIES)
            self.assertTrue(i["title"] and i["description"] and i["source"] and i["calculation"], i["id"])
            self.assertTrue(i["data"], i["id"])
            self.assertIn(i["drill"]["screen"], DRILL_SCREENS, i["id"])

    def test_an_unfinished_period_is_compared_like_for_like(self) -> None:
        # one invoice late in the previous month would make this month look bad if the whole month were the base
        _invoice(self.c1, self.item_a, 10, 100, add_days(self.this_first, -1))  # last day of the previous month
        _invoice(self.c1, self.item_a, 1, 100, self.this_first)
        d = self.feed()
        last_of_this = getdate(add_days(add_months(self.this_first, 1), -1))
        if getdate(today()) < last_of_this:
            window_end = min(add_days(self.prev_first, getdate(today()).day - 1), add_days(self.this_first, -1))
            self.assertTrue(d["comparison_note"])
            self.assertEqual(d["compared_with"]["to"], str(window_end))
            if window_end < add_days(self.this_first, -1):  # the previous month's last day is outside the comparable days
                self.assertNotIn("sales_decline", _ids(d))
        # a finished period is compared whole
        last = self.feed(preset="last_month")
        self.assertIsNone(last["comparison_note"])

    # -- growth and mix ------------------------------------------------------------------------------------------------

    def test_growth_concentration_and_movers(self) -> None:
        _invoice(self.c1, self.item_a, 1, 100, self.prev_first)
        _invoice(self.c1, self.item_a, 8, 100, self.this_first)  # 800
        _invoice(self.c2, self.item_b, 2, 100, self.this_first)  # 200
        items = _ids(self.feed())
        self.assertEqual(items["sales_growth"]["type"], "insight")
        self.assertEqual(items["sales_growth"]["change_percent"], 900.0)
        self.assertEqual(items["customer_concentration"]["severity"], "medium")
        self.assertEqual(items["customer_concentration"]["current_value"], 80.0)
        self.assertEqual(items["top_category"]["severity"], "medium")  # 80% in one of two categories
        self.assertEqual(items[f"category_growth:{self.cat_a}"]["current_value"], 800.0)
        self.assertEqual(items[f"product_growth:{self.item_a}"]["drill"]["filters"], {"product": self.item_a})
        self.assertNotIn("sales_decline", items)

    def test_a_loss_is_critical_when_the_previous_period_was_profitable(self) -> None:
        sup = _supplier()
        _invoice(self.c1, self.item_a, 10, 100, self.prev_first)
        _invoice(self.c1, self.item_a, 1, 100, self.this_first)
        _purchase(sup, self.item_a, 20, 25, self.this_first)  # 500 of expense
        loss = _ids(self.feed())["net_loss"]
        self.assertEqual((loss["severity"], loss["current_value"], loss["previous_value"]), ("critical", -400.0, 1000.0))
        self.assertEqual(loss["drill"]["tab"], "profit_and_loss")

    def test_cash_may_not_cover_payables_due_soon(self) -> None:
        sup = _supplier()
        doc = frappe.get_doc(
            {
                "doctype": "Purchase Invoice", "company": COMPANY, "supplier": sup, "posting_date": self.this_first, "set_posting_time": 1,
                "due_date": add_days(today(), 10), "update_stock": 0,
                "items": [{"item_code": self.item_a, "qty": 4, "rate": 125, "expense_account": _expense_account()}],
            }
        ).insert(ignore_permissions=True)
        doc.submit()
        alert = _ids(self.feed())["cash_cover"]
        self.assertEqual((alert["severity"], alert["current_value"]), ("high", 0.0))
        self.assertEqual({r["label"]: r["value"] for r in alert["data"]}, {"Cash + bank": 0.0, "Payables due in 30 days": 500.0})

    def test_nothing_to_report_when_there_is_no_previous_period_to_compare(self) -> None:
        _invoice(self.c1, self.item_a, 5, 100, self.this_first)
        ids = _ids(self.feed())
        self.assertNotIn("sales_decline", ids)
        self.assertNotIn("sales_growth", ids)  # a previous figure of 0 is not a growth rate
        self.assertNotIn("profit_decline", ids)

    # -- inventory -----------------------------------------------------------------------------------------------------

    def test_stock_alerts_link_to_their_lists(self) -> None:
        abbr = frappe.db.get_value("Company", COMPANY, "abbr")
        wh = f"MyBis Stock - {abbr}"
        if not frappe.db.exists("Warehouse", wh):
            frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "MyBis Stock", "company": COMPANY}).insert(ignore_permissions=True)

        def stock_item(qty):
            code = f"MYBIS-STK-{random_string(6).upper()}"
            frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": self.cat_a, "stock_uom": "Nos", "is_stock_item": 1}).insert(ignore_permissions=True)
            frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY, "items": [{"item_code": code, "qty": qty, "basic_rate": 10, "t_warehouse": wh}]}).insert(ignore_permissions=True).submit()
            return code

        low, gone = stock_item(5), stock_item(3)
        frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Issue", "company": COMPANY, "items": [{"item_code": gone, "qty": 3, "basic_rate": 10, "s_warehouse": wh}]}).insert(ignore_permissions=True).submit()
        item = frappe.get_doc("Item", low)
        item.append("reorder_levels", {"warehouse": wh, "warehouse_reorder_level": 20, "warehouse_reorder_qty": 50, "material_request_type": "Purchase"})
        item.save(ignore_permissions=True)
        items = _ids(self.feed())
        self.assertEqual(items["low_stock"]["drill"], {"screen": "inventory", "kind": "low_stock"})
        self.assertEqual(items["out_of_stock"]["drill"], {"screen": "inventory", "kind": "out_of_stock"})
        self.assertGreaterEqual(items["out_of_stock"]["current_value"], 1)
        self.assertEqual(items["low_stock"]["severity"], "medium")  # fewer than 10 items

    # -- permissions and endpoints -------------------------------------------------------------------------------------

    def test_rules_whose_source_is_not_readable_are_skipped_not_guessed(self) -> None:
        """Simulates a user who may read Sales Invoices but not the ledger (the permission itself is covered in test_mybis_dashboard)."""
        _invoice(self.c1, self.item_a, 10, 100, self.prev_first)
        _invoice(self.c1, self.item_a, 1, 100, self.this_first)
        with patch.object(insights, "_can", side_effect=lambda *kinds: "gl" not in kinds):
            d = alerts_api.feed(company=COMPANY, refresh=1)["data"]
        ids = _ids(d)
        self.assertIn("sales_decline", ids)
        self.assertNotIn("profit_decline", ids)
        self.assertNotIn("receivables_overdue", ids)
        self.assertNotIn("cash_cover", ids)
        self.assertEqual(set(d["skipped_rules"]), {"profit", "expenses", "receivables", "payables", "cash"})

    def test_a_rule_that_hits_a_permission_error_is_skipped(self) -> None:
        _invoice(self.c1, self.item_a, 10, 100, self.prev_first)
        _invoice(self.c1, self.item_a, 1, 100, self.this_first)
        with patch.object(insights.finance, "_execute", side_effect=frappe.PermissionError("no report access")):
            d = alerts_api.feed(company=COMPANY, refresh=1)["data"]
        self.assertIn("sales_decline", _ids(d))
        self.assertNotIn("receivables_overdue", _ids(d))
        self.assertIn("receivables", d["skipped_rules"])

    def test_summary_counts_and_top_items(self) -> None:
        _invoice(self.c1, self.item_a, 10, 100, self.prev_first)
        _invoice(self.c1, self.item_a, 1, 100, self.this_first)
        s = alerts_api.summary(company=COMPANY, refresh=1)["data"]
        full = self.feed()
        self.assertEqual(s["counts"], full["counts"])
        self.assertLessEqual(len(s["top"]), 3)
        self.assertEqual(s["top"][0]["id"], full["items"][0]["id"])
        self.assertEqual(set(s["top"][0]), {"id", "type", "severity", "title", "description", "drill"})

    def test_comparable_scope_truncates_only_unfinished_periods(self) -> None:
        cur = periods.Period(getdate("2026-10-01"), getdate("2026-10-31"))
        prev = periods.Period(getdate("2026-09-01"), getdate("2026-09-30"))
        s = Scope(COMPANY, "SAR", cur, prev, "this_month")
        used, note = insights.comparable(s, getdate("2026-10-24"))
        self.assertEqual((used.current.to_date, used.previous.to_date), (getdate("2026-10-24"), getdate("2026-09-24")))
        self.assertIn("same 24 days", note)
        done, none = insights.comparable(s, getdate("2026-11-02"))
        self.assertEqual((done.current.to_date, none), (getdate("2026-10-31"), None))
        short = periods.Period(getdate("2026-02-01"), getdate("2026-02-28"))
        used, _n = insights.comparable(Scope(COMPANY, "SAR", periods.Period(getdate("2026-03-01"), getdate("2026-03-31")), short, "this_month"), getdate("2026-03-30"))
        self.assertEqual(used.previous.to_date, getdate("2026-02-28"))  # capped at the previous period's end


class TestMyBisForecastApi(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        _company()
        frappe.db.commit()

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self.cust = _customer()
        self.item = _item(_group("MyBis Cat A"))

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _daily_sales(self, days: int, amount: float = 100.0) -> None:
        for back in range(1, days + 1):
            _invoice(self.cust, self.item, 1, amount, add_days(today(), -back))

    def test_sales_forecast_extends_actual_history_and_is_labelled(self) -> None:
        self._daily_sales(25)
        r = fc_api.project(subject="sales", horizon="7d", method="moving_average", company=COMPANY, refresh=1)["data"]
        self.assertTrue(r["available"])
        self.assertEqual((r["granularity"], r["method"], r["currency"]), ("day", "moving_average", "SAR"))
        self.assertIn("not AI", r["labels"]["forecast"])
        self.assertEqual(r["history"][-1], {"date": str(add_days(today(), -1)), "value": 100.0})
        self.assertEqual(r["forecast"][0]["date"], str(today()))  # the forecast starts where the history ends
        self.assertEqual([p["value"] for p in r["forecast"]], [100.0] * 7)
        s = r["summary"]
        self.assertEqual((s["historical_total"], s["forecast_total"], s["growth_percent"]), (700.0, 700.0, 0.0))
        self.assertEqual(r["quality"]["n_history"], 25)
        self.assertEqual(r["quality"]["confidence"], "low")
        self.assertTrue(any("data points" in x for x in r["limitations"]))
        self.assertTrue(any("History starts" in x for x in r["limitations"]))
        self.assertTrue(all(p["lower"] <= p["value"] <= p["upper"] for p in r["forecast"]))

    def test_auto_method_and_candidates_and_horizons(self) -> None:
        self._daily_sales(25)
        r = fc_api.project(subject="sales", horizon="30d", company=COMPANY, refresh=1)["data"]
        self.assertEqual(len(r["forecast"]), 30)
        self.assertEqual({c["method"] for c in r["candidates"]}, {"moving_average", "weighted_moving_average", "exponential_smoothing", "holt"})
        self.assertIn("Forecast =", r["method_note"])

    def test_revenue_forecast_comes_from_the_ledger_and_cash_flow_projects_a_balance(self) -> None:
        self._daily_sales(20)
        rev = fc_api.project(subject="revenue", horizon="7d", method="moving_average", company=COMPANY, refresh=1)["data"]
        self.assertEqual([p["value"] for p in rev["forecast"]], [100.0] * 7)
        cash = fc_api.project(subject="cash_flow", horizon="7d", company=COMPANY, refresh=1)["data"]
        if cash["available"]:  # no cash or bank postings: the history is all zeros
            self.assertEqual(cash["cash"]["balance_now"], 0.0)
            self.assertEqual(cash["cash"]["projected_end_balance"], 0.0)
        self.assertIn("known_due", cash.get("cash", {"known_due": {}}))

    def test_too_little_history_says_so_instead_of_inventing_a_forecast(self) -> None:
        _invoice(self.cust, self.item, 1, 100, add_days(today(), -2))
        r = fc_api.project(subject="sales", horizon="7d", company=COMPANY, refresh=1)["data"]
        self.assertFalse(r["available"])
        self.assertIn("at least", r["reason"])
        self.assertNotIn("forecast", r)

    def test_a_customer_forecast_needs_a_customer(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            fc_api.project(subject="customer", company=COMPANY)
        self._daily_sales(15)
        r = fc_api.project(subject="customer", party=self.cust, horizon="7d", method="moving_average", company=COMPANY, refresh=1)["data"]
        self.assertEqual(r["party"], self.cust)
        self.assertEqual(r["forecast"][0]["value"], 100.0)

    def test_bad_input_and_permissions(self) -> None:
        for kw in ({"subject": "weather"}, {"horizon": "5y"}, {"method": "neural_net"}):
            with self.assertRaises(frappe.ValidationError, msg=str(kw)):
                fc_api.project(company=COMPANY, **kw)
        email = f"mybis.fc.{random_string(8).lower()}@zatgo.test"
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "S", "send_welcome_email": 0, "roles": [{"role": "Sales User"}]}).insert(ignore_permissions=True)
        frappe.clear_cache(user=email)
        frappe.set_user(email)
        if not frappe.has_permission("GL Entry", "read"):
            with self.assertRaises(frappe.PermissionError):
                fc_api.project(subject="revenue", company=COMPANY)
        self.assertIn("holt", fc_api.methods()["data"]["methods"])

    def test_demand_compares_forecast_with_stock_and_orders(self) -> None:
        abbr = frappe.db.get_value("Company", COMPANY, "abbr")
        wh = f"MyBis Stock - {abbr}"
        if not frappe.db.exists("Warehouse", wh):
            frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "MyBis Stock", "company": COMPANY}).insert(ignore_permissions=True)
        code = f"MYBIS-DEM-{random_string(6).upper()}"
        frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": _group("MyBis Cat A"), "stock_uom": "Nos", "is_stock_item": 1}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": COMPANY, "posting_date": add_days(today(), -30), "set_posting_time": 1, "items": [{"item_code": code, "qty": 80, "basic_rate": 10, "t_warehouse": wh}]}).insert(ignore_permissions=True).submit()
        for back in range(1, 17):
            d = add_days(today(), -back)
            frappe.get_doc(
                {"doctype": "Sales Invoice", "company": COMPANY, "customer": self.cust, "posting_date": d, "set_posting_time": 1, "due_date": d, "update_stock": 1,
                 "items": [{"item_code": code, "qty": 2, "rate": 30, "warehouse": wh}]}
            ).insert(ignore_permissions=True).submit()
        r = fc_api.demand(horizon_days=30, company=COMPANY, refresh=1)["data"]
        row = next(x for x in r["rows"] if x["item_code"] == code)
        self.assertEqual((row["sold_90d"], row["avg_daily"], row["stock"], row["on_order"]), (32.0, 2.0, 48.0, 0.0))
        self.assertEqual(row["forecast_demand"], 60.0)
        self.assertEqual(row["suggested_reorder"], 12.0)  # 60 - 48 - 0
        self.assertEqual(row["days_of_cover"], 24.0)
        self.assertIn("no purchase order is created", r["note"])
