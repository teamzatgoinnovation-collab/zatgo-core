"""Resto POS back-office: profile, menu items, stock adjust (idempotent Stock
Entry), payments list, customers and dashboard counts."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string, today

from zatgo_core.services import resto_pos_admin_service as admin
from zatgo_core.services import resto_pos_service as svc
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)
from zatgo_core.tests.integration.test_resto_pos_order_to_payment import (
    TestRestoPosOrderToPayment as _Base,
)


class TestRestoPosAdmin(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        _Base.company = cls.company
        cls.warehouse = _Base._make_warehouse("RestoPosAdminTest")
        cash_account = frappe.db.get_value(
            "Account", {"account_type": "Cash", "company": cls.company, "is_group": 0}, "name"
        )
        get_or_create_cash_mode_of_payment(cls.company, cash_account)
        frappe.db.commit()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    def test_profile(self) -> None:
        res = admin.get_profile()
        self.assertTrue(res["success"])
        self.assertIn("industries", res["data"])
        self.assertIsInstance(res["data"]["payment_modes"], list)

    def test_item_upsert_and_disable(self) -> None:
        code = f"POSADM-{random_string(6).upper()}"
        created = admin.upsert_item(item_code=code, item_name="Admin Burger", price=12.5, barcode=f"BC{code}")
        self.assertTrue(created["success"], created.get("error"))
        self.assertEqual(frappe.db.get_value("Item", code, "standard_rate"), 12.5)
        admin.upsert_item(item_code=code, price=15)
        self.assertEqual(frappe.db.get_value("Item", code, "standard_rate"), 15)
        found = admin.find_by_barcode(f"BC{code}")
        self.assertTrue(found["data"])
        admin.disable_item(code)
        self.assertEqual(frappe.db.get_value("Item", code, "disabled"), 1)

    def test_stock_adjust_is_idempotent(self) -> None:
        code = f"POSADM-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=10)
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        cid = f"adj-{random_string(8)}"
        first = admin.adjust_stock(code, 7, cid, warehouse=self.warehouse, company=self.company)
        self.assertTrue(first["success"], first.get("error"))
        second = admin.adjust_stock(code, 7, cid, warehouse=self.warehouse, company=self.company)
        self.assertTrue(second["meta"]["idempotent"])
        self.assertEqual(frappe.db.count("Stock Entry", {"zatgo_client_id": cid}), 1)
        self.assertEqual(
            frappe.db.get_value("Bin", {"item_code": code, "warehouse": self.warehouse}, "actual_qty"), 7
        )
        admin.adjust_stock(code, -3, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)
        self.assertEqual(
            frappe.db.get_value("Bin", {"item_code": code, "warehouse": self.warehouse}, "actual_qty"), 4
        )
        rows = admin.list_stock(self.warehouse, company=self.company)["data"]
        self.assertEqual(next(r for r in rows if r["id"] == code)["onHand"], 4)
        with self.assertRaises(frappe.ValidationError):
            admin.adjust_stock(code, 0, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)

    def test_customers(self) -> None:
        name = f"POS Cust {random_string(5)}"
        created = admin.upsert_customer(customer_name=name, phone="0500000000")
        cid = created["data"]["id"]
        listed = admin.list_customers(search=name)["data"]
        self.assertTrue(any(c["id"] == cid for c in listed))
        updated = admin.upsert_customer(customer_id=cid, phone="0511111111")
        self.assertEqual(updated["data"]["phone"], "0511111111")

    def test_payments_and_dashboard(self) -> None:
        code = f"POSADM-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=10)
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        admin.adjust_stock(code, 10, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)
        if frappe.db.exists("ZG Company Settings", self.company):
            frappe.db.set_value("ZG Company Settings", self.company, "default_warehouse", self.warehouse)
        order = svc.create_order(
            company=self.company,
            channel="counter",
            items=[{"item_code": code, "qty": 1, "rate": 10}],
            client_id=f"adm-order-{random_string(8)}",
        )
        order_id = order["data"]["id"]
        paid = svc.pay(order_id, "cash", f"adm-pay-{random_string(8)}")
        self.assertTrue(paid["success"], paid.get("error"))
        payments = admin.list_payments(date=today())["data"]
        self.assertTrue(any(p["orderId"] == order_id and p["method"] == "cash" for p in payments))
        counts = admin.dashboard_counts()["data"]
        self.assertGreaterEqual(counts["paymentsToday"], 1)
        self.assertGreaterEqual(counts["todaySales"], 10)

    def test_pay_applies_discount_on_invoice(self) -> None:
        code = f"POSADM-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=10)
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        admin.adjust_stock(code, 10, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)
        if frappe.db.exists("ZG Company Settings", self.company):
            frappe.db.set_value("ZG Company Settings", self.company, "default_warehouse", self.warehouse)
        order = svc.create_order(
            company=self.company,
            channel="counter",
            items=[{"item_code": code, "qty": 2, "rate": 10}],
            client_id=f"disc-order-{random_string(8)}",
        )
        order_id = order["data"]["id"]
        with self.assertRaises(frappe.ValidationError):
            svc.pay(order_id, "cash", f"disc-bad-{random_string(8)}", "fixed", 999)
        paid = svc.pay(order_id, "cash", f"disc-pay-{random_string(8)}", "percent", 10)
        self.assertTrue(paid["success"], paid.get("error"))
        si = frappe.get_doc("Sales Invoice", frappe.db.get_value("ZG Order", order_id, "sales_invoice"))
        self.assertEqual(si.net_total, 18)  # 20 less 10%
        self.assertEqual(paid["data"]["payment"]["amount"], si.grand_total)
