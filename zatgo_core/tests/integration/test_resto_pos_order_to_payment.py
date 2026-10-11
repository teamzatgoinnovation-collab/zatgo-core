"""Money-path integration coverage for the resto POS order/table/billing
domain: table seat -> order -> send (KDS) -> mark billing -> pay (Sales
Invoice + Payment Entry), plus idempotency, void, and walk-in-customer
auto-creation."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.services import resto_pos_service as svc
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)


class TestRestoPosOrderToPayment(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.warehouse = cls._make_warehouse("RestoPosTest")
        cls.item_code = cls._make_stocked_item(cls.warehouse, qty=50)

        cash_account = frappe.db.get_value(
            "Account", {"account_type": "Cash", "company": cls.company, "is_group": 0}, "name"
        )
        get_or_create_cash_mode_of_payment(cls.company, cash_account)

        # Pin the warehouse this test's checkouts resolve to — the test
        # company is shared across integration test files, so "first
        # warehouse for this company" would otherwise be nondeterministic.
        if frappe.db.exists("ZG Company Settings", cls.company):
            settings = frappe.get_doc("ZG Company Settings", cls.company)
            settings.default_warehouse = cls.warehouse
            settings.save(ignore_permissions=True)
        else:
            frappe.get_doc(
                {
                    "doctype": "ZG Company Settings",
                    "company": cls.company,
                    "default_warehouse": cls.warehouse,
                }
            ).insert(ignore_permissions=True)
        frappe.db.commit()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures -----------------------------------------------------------

    @classmethod
    def _make_warehouse(cls, label: str) -> str:
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        name = f"{label} - {abbr}" if abbr else label
        if frappe.db.exists("Warehouse", name):
            return name
        doc = frappe.get_doc(
            {"doctype": "Warehouse", "warehouse_name": label, "company": cls.company}
        )
        doc.insert(ignore_permissions=True)
        return doc.name

    @classmethod
    def _make_stocked_item(cls, warehouse: str, qty: float) -> str:
        code = f"RESTOPOS-TEST-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": 1,
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": cls.company,
                "items": [{"item_code": code, "qty": qty, "t_warehouse": warehouse, "basic_rate": 10}],
            }
        ).insert(ignore_permissions=True).submit()
        return code

    @classmethod
    def _make_table(cls, label: str) -> str:
        code = f"T-{random_string(4).upper()}"
        frappe.get_doc(
            {
                "doctype": "ZG Table",
                "table_code": code,
                "table_name": label,
                "company": cls.company,
            }
        ).insert(ignore_permissions=True)
        return code

    # -- tests ----------------------------------------------------------------

    def test_full_dine_in_flow(self) -> None:
        table = self._make_table("Dine-in Test Table")
        item = self._make_stocked_item(self.warehouse, qty=20)

        seated = svc.seat_table(table, covers=2, client_id=f"test-seat-{random_string(8)}")
        self.assertTrue(seated["success"], seated.get("error"))
        order_id = seated["data"]["id"]
        self.assertEqual(seated["data"]["status"], "open")
        self.assertEqual(frappe.db.get_value("ZG Table", table, "status"), "Occupied")

        added = svc.add_item(order_id, item, qty=2, rate=10)
        self.assertTrue(added["success"], added.get("error"))
        self.assertEqual(len(added["data"]["items"]), 1)

        sent = svc.send_order(order_id)
        self.assertTrue(sent["success"], sent.get("error"))
        self.assertEqual(sent["data"]["status"], "sent")
        self.assertEqual(frappe.db.count("ZG KDS Ticket", {"order_number": sent["data"]["number"]}), 1)

        billed = svc.mark_billing(order_id)
        self.assertTrue(billed["success"], billed.get("error"))
        self.assertEqual(frappe.db.get_value("ZG Table", table, "status"), "Billing")

        paid = svc.pay(order_id, "cash", f"test-pay-{random_string(8)}")
        self.assertTrue(paid["success"], paid.get("error"))
        self.assertEqual(paid["data"]["order"]["status"], "paid")

        si_name = frappe.db.get_value("ZG Order", order_id, "sales_invoice")
        pe_name = frappe.db.get_value("ZG Order", order_id, "payment_entry")
        self.assertEqual(frappe.db.get_value("Sales Invoice", si_name, "docstatus"), 1)
        self.assertEqual(frappe.db.get_value("Sales Invoice", si_name, "update_stock"), 1)
        self.assertEqual(frappe.db.get_value("Sales Invoice", si_name, "outstanding_amount"), 0)
        self.assertEqual(frappe.db.get_value("Payment Entry", pe_name, "docstatus"), 1)

        remaining_qty = frappe.db.get_value(
            "Bin", {"item_code": item, "warehouse": self.warehouse}, "actual_qty"
        )
        self.assertEqual(remaining_qty, 18)  # 20 received - 2 sold

    def test_walk_in_flow(self) -> None:
        item = self._make_stocked_item(self.warehouse, qty=10)
        created = svc.create_order(
            # The test company: the user's default company (any on a shared
            # bench) would pick a warehouse without this test's stock.
            company=self.company,
            channel="counter",
            items=[{"item_code": item, "qty": 1, "rate": 10}],
            client_id=f"test-walkin-{random_string(8)}",
        )
        self.assertTrue(created["success"], created.get("error"))
        order_id = created["data"]["id"]

        paid = svc.pay(order_id, "cash", f"test-walkin-pay-{random_string(8)}")
        self.assertTrue(paid["success"], paid.get("error"))
        self.assertEqual(paid["data"]["order"]["status"], "paid")
        self.assertEqual(paid["data"]["payment"]["amount"], 10)

    def test_pay_is_idempotent(self) -> None:
        item = self._make_stocked_item(self.warehouse, qty=10)
        created = svc.create_order(
            # The test company: the user's default company (any on a shared
            # bench) would pick a warehouse without this test's stock.
            company=self.company,
            channel="counter",
            items=[{"item_code": item, "qty": 1, "rate": 10}],
            client_id=f"test-idem-order-{random_string(8)}",
        )
        order_id = created["data"]["id"]
        client_id = f"test-idem-pay-{random_string(8)}"

        first = svc.pay(order_id, "cash", client_id)
        self.assertTrue(first["success"], first.get("error"))
        second = svc.pay(order_id, "cash", client_id)
        self.assertTrue(second["success"], second.get("error"))
        self.assertTrue(second["meta"]["idempotent"])

        si_name = frappe.db.get_value("ZG Order", order_id, "sales_invoice")
        self.assertEqual(
            frappe.db.count("Sales Invoice", {"zatgo_client_id": client_id}), 1
        )
        self.assertEqual(
            frappe.db.count("Payment Entry", {"zatgo_client_id": f"{client_id}:pay"}), 1
        )
        self.assertEqual(first["data"]["order"]["id"], second["data"]["order"]["id"])
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", si_name, "outstanding_amount"), 0
        )

    def test_void_before_payment_creates_no_invoice(self) -> None:
        table = self._make_table("Void Test Table")
        item = self._make_stocked_item(self.warehouse, qty=10)
        created = svc.create_order(
            # The test company: the user's default company (any on a shared
            # bench) would pick a warehouse without this test's stock.
            company=self.company,
            table=table,
            channel="dine_in",
            items=[{"item_code": item, "qty": 1, "rate": 10}],
            client_id=f"test-void-{random_string(8)}",
        )
        order_id = created["data"]["id"]

        voided = svc.void_order(order_id)
        self.assertTrue(voided["success"], voided.get("error"))
        self.assertEqual(voided["data"]["status"], "void")
        self.assertIsNone(frappe.db.get_value("ZG Order", order_id, "sales_invoice"))
        self.assertEqual(frappe.db.get_value("ZG Table", table, "status"), "Free")
        self.assertIsNone(frappe.db.get_value("ZG Table", table, "current_order"))

    def test_walk_in_customer_auto_created(self) -> None:
        if frappe.db.exists("Customer", "Walk-in Customer"):
            frappe.delete_doc("Customer", "Walk-in Customer", ignore_permissions=True, force=True)

        item = self._make_stocked_item(self.warehouse, qty=10)
        created = svc.create_order(
            # The test company: the user's default company (any on a shared
            # bench) would pick a warehouse without this test's stock.
            company=self.company,
            channel="counter",
            items=[{"item_code": item, "qty": 1, "rate": 10}],
            client_id=f"test-walkincust-{random_string(8)}",
        )
        order_id = created["data"]["id"]
        paid = svc.pay(order_id, "cash", f"test-walkincust-pay-{random_string(8)}")
        self.assertTrue(paid["success"], paid.get("error"))

        self.assertTrue(frappe.db.exists("Customer", "Walk-in Customer"))
        si_name = frappe.db.get_value("ZG Order", order_id, "sales_invoice")
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", si_name, "customer"), "Walk-in Customer"
        )
