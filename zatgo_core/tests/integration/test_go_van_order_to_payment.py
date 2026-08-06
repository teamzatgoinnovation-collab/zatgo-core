"""Money-path integration coverage: order -> stock deduction -> collection.

Flagged as zero-coverage in the Phase 1 audit. Also regression-protects the
authorization fixes made alongside it: a non-admin caller must not be able to
create an order against a warehouse that isn't theirs, or collect payment
from a customer that isn't on their route.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.services.go_van_service import create_collection, create_order


class TestGoVanOrderToPayment(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = frappe.db.get_value("Company", {}, "name")
        if not cls.company:
            frappe.throw("No Company found — run install_fixtures before this test.")
        cls.own_warehouse = cls._make_warehouse("VanSaleTestOwn")
        cls.other_warehouse = cls._make_warehouse("VanSaleTestOther")
        cls.item_code = cls._make_stocked_item(cls.own_warehouse, qty=50)
        cls.own_customer = cls._make_customer("VanSale Test Own Customer")
        cls.other_customer = cls._make_customer("VanSale Test Other Customer")
        cls.van_user = cls._make_van_user(cls.own_warehouse)
        cls._make_trip(cls.van_user, cls.own_customer, cls.own_warehouse)

    def setUp(self) -> None:
        frappe.set_user(self.van_user)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures ---------------------------------------------------------

    @classmethod
    def _make_warehouse(cls, label: str) -> str:
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        name = f"{label} - {abbr}" if abbr else label
        if frappe.db.exists("Warehouse", name):
            return name
        doc = frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": label,
                "company": cls.company,
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name

    @classmethod
    def _make_stocked_item(cls, warehouse: str, qty: float) -> str:
        code = f"VANSALE-TEST-{random_string(6).upper()}"
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
                "items": [
                    {
                        "item_code": code,
                        "qty": qty,
                        "t_warehouse": warehouse,
                        "basic_rate": 10,
                    }
                ],
            }
        ).insert(ignore_permissions=True).submit()
        return code

    @classmethod
    def _make_customer(cls, name: str) -> str:
        if frappe.db.exists("Customer", name):
            return name
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Individual",
                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name

    @classmethod
    def _make_van_user(cls, warehouse: str) -> str:
        email = f"vansale.audit.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "AuditTest",
                "send_welcome_email": 0,
                "roles": [{"role": "VanSale User"}],
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "ZG Van Sale Profile",
                "user": email,
                "enabled": 1,
                "user_type": "Field User",
                "warehouse": warehouse,
            }
        ).insert(ignore_permissions=True)
        return email

    @classmethod
    def _make_trip(cls, user: str, customer: str, warehouse: str) -> None:
        frappe.get_doc(
            {
                "doctype": "ZG Trip",
                "title": "Audit Test Route",
                "customer": customer,
                "sequence": 1,
                "status": "Planned",
                "sales_user": user,
                "warehouse": warehouse,
            }
        ).insert(ignore_permissions=True)

    # -- tests --------------------------------------------------------------

    def test_full_order_to_payment_flow(self) -> None:
        """A VanSale User can sell to their own customer/warehouse and collect payment."""
        order = create_order(
            client_id=f"test-order-{random_string(8)}",
            customer=self.own_customer,
            items=[{"item_code": self.item_code, "qty": 2, "rate": 10}],
            warehouse=self.own_warehouse,
        )
        self.assertTrue(order["success"], order.get("error"))
        si_name = order["data"]["erp_name"]
        self.assertEqual(frappe.db.get_value("Sales Invoice", si_name, "docstatus"), 1)

        remaining_qty = frappe.db.get_value(
            "Bin", {"item_code": self.item_code, "warehouse": self.own_warehouse}, "actual_qty"
        )
        self.assertEqual(remaining_qty, 48)  # 50 received - 2 sold

        collection = create_collection(
            client_id=f"test-collect-{random_string(8)}",
            customer=self.own_customer,
            amount=20,
            sales_invoice=si_name,
        )
        self.assertTrue(collection["success"], collection.get("error"))
        self.assertEqual(frappe.db.get_value("Sales Invoice", si_name, "outstanding_amount"), 0)

    def test_order_rejects_warehouse_not_owned_by_caller(self) -> None:
        """A non-admin cannot create an order against a warehouse that isn't theirs."""
        with self.assertRaises(frappe.PermissionError):
            create_order(
                client_id=f"test-order-{random_string(8)}",
                customer=self.own_customer,
                items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
                warehouse=self.other_warehouse,
            )

    def test_collection_rejects_customer_not_on_callers_route(self) -> None:
        """A non-admin cannot collect from a customer that isn't on their route."""
        with self.assertRaises(frappe.PermissionError):
            create_collection(
                client_id=f"test-collect-{random_string(8)}",
                customer=self.other_customer,
                amount=10,
            )
