"""Coverage for vansalex.orders.list_sales_orders.

The VanSaleX app has no local store, so the Order -> Confirm -> Invoice
flow's pending orders have to come from the server: a field user must see
only their own Sales Orders, each with its lines, and — once confirmed —
the Sales Invoice it became.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1.vansalex.orders import list_sales_orders
from zatgo_core.services.vansalex_service import confirm_order, create_sales_order
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestVansalexSalesOrderList(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.warehouse = cls._make_warehouse("VanSaleSOListTest")
        cls.item_code = cls._make_stocked_item(cls.warehouse, qty=1000)

    def setUp(self) -> None:
        # create_sales_order()/confirm_order() commit for real — fresh users
        # and customer per test keep one test's orders out of another's list.
        self.van_user = self._make_van_user(self.warehouse)
        self.other_user = self._make_van_user(self.warehouse)
        self.customer = self._make_customer(f"SO List {random_string(8)}")

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures (mirrors test_vansalex_collection_allocation.py) --------

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
        code = f"VANSALE-SOLIST-{random_string(6).upper()}"
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
                    {"item_code": code, "qty": qty, "t_warehouse": warehouse, "basic_rate": 10}
                ],
            }
        ).insert(ignore_permissions=True).submit()
        return code

    @classmethod
    def _make_customer(cls, name: str) -> str:
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
        email = f"vansale.solist.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "SOListTest",
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

    def _place_order(self, user: str, qty: float = 2) -> str:
        frappe.set_user(user)
        result = create_sales_order(
            client_id=f"test-so-{random_string(8)}",
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": qty, "rate": 10}],
            company=self.company,
        )
        frappe.set_user("Administrator")
        self.assertTrue(result["success"], result.get("error"))
        return result["data"]["erp_name"]

    # -- tests --------------------------------------------------------------

    def test_field_user_sees_only_own_orders_with_lines(self) -> None:
        mine = self._place_order(self.van_user, qty=3)
        theirs = self._place_order(self.other_user)

        frappe.set_user(self.van_user)
        rows = list_sales_orders(page_size=100)["data"]
        names = {r["name"] for r in rows}
        self.assertIn(mine, names)
        self.assertNotIn(theirs, names)

        row = next(r for r in rows if r["name"] == mine)
        self.assertEqual(row["customer_id"], self.customer)
        self.assertIsNone(row["sales_invoice"])
        self.assertEqual(
            row["items"],
            [{"item_code": self.item_code, "item_name": self.item_code, "qty": 3.0, "rate": 10.0}],
        )

    def test_confirmed_order_reports_its_invoice(self) -> None:
        so = self._place_order(self.van_user)
        frappe.set_user(self.van_user)
        confirmed = confirm_order(
            client_id=f"test-confirm-{random_string(8)}",
            sales_order=so,
            warehouse=self.warehouse,
        )
        self.assertTrue(confirmed["success"], confirmed.get("error"))

        row = next(r for r in list_sales_orders(page_size=100)["data"] if r["name"] == so)
        self.assertEqual(row["sales_invoice"], confirmed["data"]["erp_name"])
        self.assertEqual(row["per_billed"], 100.0)
