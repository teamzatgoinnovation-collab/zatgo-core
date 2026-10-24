"""MyBis sales / purchase breakdowns, the drill-down chain and inventory analytics against real ERPNext documents."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import add_days, getdate, random_string, today

from zatgo_core.api.v1.mybis import inventory as inv_api
from zatgo_core.api.v1.mybis import purchase as pur_api
from zatgo_core.api.v1.mybis import sales as sales_api
from zatgo_core.tests.integration._fixtures import get_or_create_test_company
from zatgo_core.tests.integration.test_mybis_dashboard import COMPANY, _company, _customer, _group, _invoice, _item


def _supplier() -> str:
    doc = frappe.get_doc(
        {
            "doctype": "Supplier",
            "supplier_name": f"MyBis Supp {random_string(6)}",
            "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
        }
    )
    doc.insert(ignore_permissions=True)
    return doc.name


def _expense_account() -> str:
    return frappe.db.get_value("Account", {"company": COMPANY, "root_type": "Expense", "is_group": 0, "account_type": ["in", ["", None]]}, "name") or frappe.db.get_value(
        "Account", {"company": COMPANY, "root_type": "Expense", "is_group": 0}, "name"
    )


def _purchase(supplier: str, item: str, qty: float, rate: float, posting_date) -> str:
    doc = frappe.get_doc(
        {
            "doctype": "Purchase Invoice",
            "company": COMPANY,
            "supplier": supplier,
            "posting_date": posting_date,
            "set_posting_time": 1,
            "due_date": posting_date,
            "update_stock": 0,
            "items": [{"item_code": item, "qty": qty, "rate": rate, "expense_account": _expense_account()}],
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


class TestMyBisSalesAnalytics(IntegrationTestCase):
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
        self.this_day = getdate(today()).replace(day=1)
        self.last_day = add_days(self.this_day, -3)
        self.inv_a = _invoice(self.cust, self.item_a, 2, 100, self.this_day)
        self.inv_b = _invoice(self.cust, self.item_b, 1, 50, self.this_day)
        _invoice(self.cust, self.item_b, 1, 50, self.this_day, return_against=self.inv_b)
        _invoice(self.cust, self.item_a, 1, 100, self.last_day)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _by(self, dimension, **kw):
        return sales_api.breakdown_by(dimension=dimension, company=COMPANY, preset="this_month", **kw)["data"]

    def test_summary_figures_and_paid_credit_split_add_up(self) -> None:
        s = sales_api.summary(company=COMPANY, preset="this_month")["data"]
        self.assertEqual(s["gross_sales"]["value"], 250.0)
        self.assertEqual(s["net_sales"]["value"], 200.0)
        self.assertEqual(s["returns"]["value"], -50.0)
        self.assertEqual(s["invoices"]["value"], 2)
        self.assertEqual(s["average_order_value"]["value"], 125.0)
        self.assertAlmostEqual(s["paid_sales"]["value"] + s["credit_sales"]["value"], 250.0, places=2)
        self.assertIn(s["gross_profit"]["basis"], ("gl", "valuation_estimate"))

    def test_breakdown_by_category_nets_returns_and_drops_empty_rows(self) -> None:
        d = self._by("category")
        rows = {r["code"]: r for r in d["rows"]}
        self.assertEqual(rows[self.cat_a]["revenue"], 200.0)
        self.assertNotIn(self.cat_b, rows)
        self.assertEqual(rows[self.cat_a]["previous_revenue"], 100.0)
        self.assertEqual(rows[self.cat_a]["growth_percent"], 100.0)
        self.assertEqual(rows[self.cat_a]["share_percent"], 100.0)
        self.assertEqual(d["total_revenue"], 200.0)

    def test_item_level_rows_carry_estimated_profit(self) -> None:
        r = self._by("product")["rows"][0]
        self.assertEqual(r["code"], self.item_a)
        self.assertEqual(r["quantity"], 2.0)
        self.assertEqual(r["profit"], r["revenue"] - r["cost"])  # non-stock item: no valuation cost

    def test_by_customer_and_warehouse(self) -> None:
        c = self._by("customer")["rows"][0]
        self.assertEqual((c["code"], c["revenue"], c["invoices"]), (self.cust, 200.0, 2))
        w = self._by("warehouse")["rows"]
        self.assertEqual(w[0]["code"], "(none)")  # non-stock items have no warehouse

    def test_drill_down_chain_category_product_invoices_detail(self) -> None:
        prods = self._by("product", filters={"category": self.cat_a})
        self.assertEqual([r["code"] for r in prods["rows"]], [self.item_a])
        invs = sales_api.invoices(company=COMPANY, preset="this_month", filters={"category": self.cat_a, "product": self.item_a})
        self.assertEqual([r["name"] for r in invs["data"]], [self.inv_a])
        self.assertEqual(invs["data"][0]["amount"], 200.0)
        self.assertEqual(invs["meta"]["total"], 1)
        detail = sales_api.invoice_detail(self.inv_a)["data"]
        self.assertEqual(detail["items"][0]["item_code"], self.item_a)
        self.assertEqual(detail["party"], self.cust)
        self.assertEqual(detail["grand_total"], 200.0)

    def test_invoice_list_pages_newest_first_and_includes_returns(self) -> None:
        p1 = sales_api.invoices(company=COMPANY, preset="this_month", page=1, page_size=2)
        self.assertEqual(len(p1["data"]), 2)
        self.assertEqual(p1["meta"]["total"], 3)  # two invoices and the return
        p2 = sales_api.invoices(company=COMPANY, preset="this_month", page=2, page_size=2)
        self.assertEqual(len(p2["data"]), 1)
        self.assertTrue(any(r["is_return"] for r in p1["data"] + p2["data"]))

    def test_bad_input_is_refused(self) -> None:
        for kw in ({"dimension": "color"}, {"dimension": "product", "filters": {"salesperson": "x"}}, {"dimension": "salesperson", "filters": {"category": "x"}}, {"dimension": "product", "order": "weight"}):
            with self.assertRaises(frappe.ValidationError, msg=str(kw)):
                sales_api.breakdown_by(company=COMPANY, **kw)
        with self.assertRaises(frappe.ValidationError):
            sales_api.breakdown_by(company=COMPANY, dimension="product", filters="not json")

    def test_sql_injection_in_a_filter_value_is_only_a_value(self) -> None:
        d = self._by("product", filters={"category": "x' OR '1'='1"})
        self.assertEqual(d["rows"], [])

    def test_salesperson_without_a_sales_team_is_empty_not_an_error(self) -> None:
        self.assertEqual(self._by("salesperson")["rows"], [])

    def test_order_by_profit_and_quantity_are_accepted(self) -> None:
        self.assertEqual(self._by("product", order="profit")["rows"][0]["code"], self.item_a)
        self.assertEqual(self._by("product", order="quantity")["rows"][0]["code"], self.item_a)

    def _more_products(self):
        """item_c: 30 -> 90 (+200%); item_d only last month (lost); item_e only this month (new)."""
        cat = _group("MyBis Cat C")
        c, d, e = _item(cat), _item(cat), _item(cat)
        _invoice(self.cust, c, 3, 30, self.this_day)
        _invoice(self.cust, c, 1, 30, self.last_day)
        _invoice(self.cust, d, 1, 40, self.last_day)
        _invoice(self.cust, e, 1, 25, self.this_day)
        return c, d, e

    def test_order_by_growth_puts_the_fastest_growing_first_and_skips_new_rows(self) -> None:
        c, _d, e = self._more_products()
        d = self._by("product", order="growth")
        codes = [r["code"] for r in d["rows"]]
        self.assertEqual(codes[:2], [c, self.item_a])  # +200% then +100%
        self.assertNotIn(e, codes)  # no previous revenue: growth is unknown, not infinite
        self.assertEqual([r["growth_percent"] for r in d["rows"][:2]], [200.0, 100.0])
        self.assertEqual(d["order"], "growth")
        self.assertGreaterEqual(d["ranked_among"], 3)

    def test_order_by_growth_needs_the_comparison(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            self._by("product", order="growth", compare=0)

    def test_movers_lists_gains_declines_new_and_lost_and_adds_up(self) -> None:
        c, d, e = self._more_products()
        m = sales_api.movers(dimension="product", company=COMPANY, preset="this_month")["data"]
        gains = {r["code"]: r for r in m["gains"]}
        self.assertEqual([r["code"] for r in m["gains"]][:2], [self.item_a, c])  # +100 then +60
        self.assertEqual(gains[e]["status"], "new")
        self.assertIsNone(gains[e]["growth_percent"])
        self.assertEqual([(r["code"], r["status"], r["change"]) for r in m["declines"]], [(d, "lost", -40.0)])
        self.assertEqual((m["revenue"], m["previous_revenue"], m["net_change"]), (315.0, 170.0, 145.0))
        self.assertEqual(m["growth_percent"], 85.29)  # 145 / 170
        self.assertEqual(m["gains_total"] + m["declines_total"], m["net_change"])
        self.assertEqual(len(sales_api.movers(dimension="product", company=COMPANY, preset="this_month", limit=1)["data"]["gains"]), 1)

    def test_movers_refuse_a_bad_dimension(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            sales_api.movers(dimension="color", company=COMPANY)

    def test_a_company_restricted_user_cannot_read_another_companys_invoice(self) -> None:
        mine = get_or_create_test_company()
        email = f"mybis.an.{random_string(8).lower()}@zatgo.test"
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "A", "send_welcome_email": 0, "roles": [{"role": "System Manager"}, {"role": "Accounts Manager"}]}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Company", "for_value": mine}).insert(ignore_permissions=True)
        frappe.clear_cache(user=email)
        frappe.set_user(email)
        with self.assertRaises(frappe.PermissionError):
            sales_api.invoice_detail(self.inv_a)
        with self.assertRaises(frappe.PermissionError):
            sales_api.invoices(company=COMPANY)


class TestMyBisPurchaseAnalytics(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        _company()
        self.sup = _supplier()
        self.cat = _group("MyBis Cat A")
        self.item = _item(self.cat)
        self.this_day = getdate(today()).replace(day=1)
        self.pi = _purchase(self.sup, self.item, 4, 25, self.this_day)
        _purchase(self.sup, self.item, 2, 25, add_days(self.this_day, -3))

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_summary(self) -> None:
        s = pur_api.summary(company=COMPANY, preset="this_month")["data"]
        self.assertEqual(s["total_purchases"]["value"], 100.0)
        self.assertEqual(s["total_purchases"]["previous_value"], 50.0)
        self.assertEqual(s["invoices"]["value"], 1)
        self.assertEqual(s["suppliers"]["value"], 1)
        self.assertEqual(s["outstanding_payables"]["value"], 150.0)  # both invoices unpaid, ledger as of period end

    def test_breakdown_and_drill(self) -> None:
        d = pur_api.breakdown_by(dimension="supplier", company=COMPANY, preset="this_month")["data"]
        self.assertEqual((d["rows"][0]["code"], d["rows"][0]["revenue"], d["rows"][0]["growth_percent"]), (self.sup, 100.0, 100.0))
        self.assertNotIn("profit", d["rows"][0])  # purchases have no profit
        drill = pur_api.breakdown_by(dimension="product", company=COMPANY, preset="this_month", filters={"supplier": self.sup})["data"]
        self.assertEqual(drill["rows"][0]["code"], self.item)
        inv = pur_api.invoices(company=COMPANY, preset="this_month", filters={"supplier": self.sup})
        self.assertEqual([r["name"] for r in inv["data"]], [self.pi])
        self.assertEqual(pur_api.invoice_detail(self.pi)["data"]["party"], self.sup)

    def test_movers(self) -> None:
        other = _item(self.cat)
        _purchase(self.sup, other, 1, 10, self.this_day)
        m = pur_api.movers(dimension="product", company=COMPANY, preset="this_month")["data"]
        self.assertEqual([r["code"] for r in m["gains"]], [self.item, other])  # +50 then a new 10
        self.assertEqual((m["revenue"], m["previous_revenue"], m["net_change"], m["growth_percent"]), (110.0, 50.0, 60.0, 120.0))
        self.assertEqual(m["declines"], [])
        g = pur_api.breakdown_by(dimension="product", company=COMPANY, preset="this_month", order="growth")["data"]
        self.assertEqual([r["code"] for r in g["rows"]], [self.item])

    def test_a_sales_only_filter_is_refused_on_purchases(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            pur_api.breakdown_by(dimension="salesperson", company=COMPANY)
        with self.assertRaises(frappe.ValidationError):
            pur_api.breakdown_by(dimension="product", company=COMPANY, filters={"customer": "x"})


class TestMyBisInventory(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        _company()
        self.abbr = frappe.db.get_value("Company", COMPANY, "abbr")
        self.wh = self._warehouse("MyBis Stock")
        self.cat = _group("MyBis Cat A")
        self.low = self._stock_item(receive=5)  # reorder level 20 -> low stock
        self.fine = self._stock_item(receive=10)
        self.gone = self._stock_item(receive=3)
        self._entry("Material Issue", self.gone, 3, source=self.wh)  # now 0 -> out of stock
        item = frappe.get_doc("Item", self.low)
        item.append("reorder_levels", {"warehouse": self.wh, "warehouse_reorder_level": 20, "warehouse_reorder_qty": 50, "material_request_type": "Purchase"})
        item.save(ignore_permissions=True)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def _warehouse(self, label: str) -> str:
        name = f"{label} - {self.abbr}"
        if not frappe.db.exists("Warehouse", name):
            frappe.get_doc({"doctype": "Warehouse", "warehouse_name": label, "company": COMPANY}).insert(ignore_permissions=True)
        return name

    def _stock_item(self, receive: float) -> str:
        code = f"MYBIS-STK-{random_string(6).upper()}"
        frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": self.cat, "stock_uom": "Nos", "is_stock_item": 1}).insert(ignore_permissions=True)
        self._entry("Material Receipt", code, receive, target=self.wh)
        return code

    def _entry(self, kind: str, code: str, qty: float, source: str | None = None, target: str | None = None) -> None:
        row = {"item_code": code, "qty": qty, "basic_rate": 10}
        if source:
            row["s_warehouse"] = source
        if target:
            row["t_warehouse"] = target
        frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": kind, "company": COMPANY, "items": [row]}).insert(ignore_permissions=True).submit()

    def test_summary_counts_and_value(self) -> None:
        s = inv_api.summary(company=COMPANY, refresh=1)["data"]
        c = s["counts"]
        self.assertEqual(c["out_of_stock"], 1)
        self.assertGreaterEqual(c["low_stock"], 1)
        self.assertGreaterEqual(c["stocked_items"], 3)
        self.assertGreaterEqual(s["stock_value"], 150.0)  # 5 + 10 units at 10 (other suites' stock may add to it)
        self.assertEqual(sum(b["items"] for b in s["idle_buckets"]), s["items_in_stock"])
        self.assertIsNotNone(s["health"]["score"])
        self.assertEqual(len(s["health"]["factors"]), 6)
        self.assertTrue(all(f["detail"] for f in s["health"]["factors"]))

    def test_alert_lists(self) -> None:
        low = inv_api.alerts(kind="low_stock", company=COMPANY)
        self.assertIn(self.low, [r["item_code"] for r in low["data"]])
        row = next(r for r in low["data"] if r["item_code"] == self.low)
        self.assertEqual((row["qty"], row["reorder_level"], row["warehouse"]), (5.0, 20.0, self.wh))
        out = inv_api.alerts(kind="out_of_stock", company=COMPANY)
        self.assertIn(self.gone, [r["item_code"] for r in out["data"]])
        self.assertNotIn(self.fine, [r["item_code"] for r in out["data"]])
        slow = inv_api.alerts(kind="slow_moving", company=COMPANY)
        self.assertIn(self.fine, [r["item_code"] for r in slow["data"]])  # received, never sold out
        self.assertEqual(low["meta"]["kind"], "low_stock")

    def test_movement_based_alerts(self) -> None:
        heavy = self._stock_item(receive=1000)
        self._entry("Material Issue", heavy, 3, source=self.wh)  # 997 left, 3 sold out in the window -> covers years
        over = inv_api.alerts(kind="overstock", company=COMPANY)
        self.assertIn(heavy, [r["item_code"] for r in over["data"]])
        self.assertNotIn(self.fine, [r["item_code"] for r in over["data"]])  # never sold: dead, not overstock
        fast = inv_api.alerts(kind="fast_moving", company=COMPANY)
        row = next(r for r in fast["data"] if r["item_code"] == heavy)
        self.assertEqual((row["sold_90d"], row["idle_days"], row["last_outward"]), (3.0, 0, str(getdate(today()))))
        s = inv_api.summary(company=COMPANY, refresh=1)["data"]
        self.assertGreaterEqual(s["counts"]["overstock_items"], 1)
        self.assertEqual(next(b for b in s["idle_buckets"] if b["bucket"] == "0-30")["items"] >= 1, True)

    def test_never_sold_means_no_outward_movement_at_all(self) -> None:
        heavy = self._stock_item(receive=50)
        self._entry("Material Issue", heavy, 1, source=self.wh)
        never = inv_api.alerts(kind="never_sold", company=COMPANY)
        codes = [r["item_code"] for r in never["data"]]
        self.assertIn(self.fine, codes)  # received 10, nothing ever left
        self.assertIn(self.low, codes)
        self.assertNotIn(heavy, codes)  # something left, so it moves (even if slowly)
        self.assertNotIn(self.gone, codes)  # nothing in stock
        row = next(r for r in never["data"] if r["item_code"] == self.fine)
        self.assertEqual((row["qty"], row["last_outward"], row["idle_days"]), (10.0, None, None))
        self.assertEqual(never["meta"]["kind"], "never_sold")

    def test_pagination_and_bad_kind(self) -> None:
        p = inv_api.alerts(kind="slow_moving", company=COMPANY, page=1, page_size=1)
        self.assertEqual(len(p["data"]), 1)
        self.assertGreaterEqual(p["meta"]["total"], 2)
        with self.assertRaises(frappe.ValidationError):
            inv_api.alerts(kind="bogus", company=COMPANY)


class TestMyBisEstimatedCost(IntegrationTestCase):
    """The valuation-estimate SQL runs only without perpetual inventory, so exercise it directly."""

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_estimated_cogs_query_is_valid_and_zero_for_service_items(self) -> None:
        from zatgo_core.services.mybis import queries

        _company()
        cust = _customer()
        item = _item(_group("MyBis Cat A"))
        _invoice(cust, item, 1, 10, getdate(today()).replace(day=1))
        start = getdate(today()).replace(day=1)
        self.assertEqual(queries.estimated_cogs(COMPANY, start, getdate(today())), 0.0)
        self.assertEqual(queries.cogs(COMPANY, start, getdate(today()), 7.0)[1] in ("gl", "valuation_estimate"), True)
