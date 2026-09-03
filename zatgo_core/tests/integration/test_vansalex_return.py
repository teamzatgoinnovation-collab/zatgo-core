"""Sales Return money-path coverage: return -> stock restored -> credit note.

Regression-protects the ownership/qty-cap checks in create_sales_return(): a
non-admin caller must not be able to return against a warehouse/invoice that
isn't theirs, and cannot return more than was originally sold.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.services.vansalex_service import create_order, create_sales_return
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestVansalexReturn(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.own_warehouse = cls._make_warehouse("VanSaleReturnTestOwn")
        cls.other_warehouse = cls._make_warehouse("VanSaleReturnTestOther")
        cls.item_code = cls._make_stocked_item(cls.own_warehouse, qty=50)
        cls.own_customer = cls._make_customer("VanSale Return Test Own Customer")
        cls.van_user = cls._make_van_user(cls.own_warehouse)
        cls.other_van_user = cls._make_van_user(cls.other_warehouse)

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
        code = f"VANSALE-RET-TEST-{random_string(6).upper()}"
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
        email = f"vansale.return.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "ReturnTest",
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

    def _make_original_order(self, qty: float = 5) -> str:
        order = create_order(
            client_id=f"test-return-order-{random_string(8)}",
            customer=self.own_customer,
            items=[{"item_code": self.item_code, "qty": qty, "rate": 10}],
            warehouse=self.own_warehouse,
            company=self.company,
        )
        self.assertTrue(order["success"], order.get("error"))
        return order["data"]["erp_name"]

    # -- tests --------------------------------------------------------------

    def test_partial_return_restores_stock_and_creates_credit_note(self) -> None:
        si_name = self._make_original_order(qty=5)
        qty_after_sale = frappe.db.get_value(
            "Bin", {"item_code": self.item_code, "warehouse": self.own_warehouse}, "actual_qty"
        )

        result = create_sales_return(
            client_id=f"test-return-{random_string(8)}",
            return_against=si_name,
            items=[{"item_code": self.item_code, "qty": 2}],
            warehouse=self.own_warehouse,
            reason="Damaged goods",
        )
        self.assertTrue(result["success"], result.get("error"))
        return_name = result["data"]["erp_name"]

        return_doc = frappe.db.get_value(
            "Sales Invoice", return_name, ["is_return", "docstatus", "grand_total", "return_against"], as_dict=True
        )
        self.assertEqual(return_doc.is_return, 1)
        self.assertEqual(return_doc.docstatus, 1)
        self.assertEqual(return_doc.return_against, si_name)
        self.assertLess(return_doc.grand_total, 0)

        qty_after_return = frappe.db.get_value(
            "Bin", {"item_code": self.item_code, "warehouse": self.own_warehouse}, "actual_qty"
        )
        self.assertEqual(qty_after_return, qty_after_sale + 2)

    def test_return_rejects_qty_exceeding_original_sale(self) -> None:
        si_name = self._make_original_order(qty=3)
        with self.assertRaises(frappe.ValidationError):
            create_sales_return(
                client_id=f"test-return-{random_string(8)}",
                return_against=si_name,
                items=[{"item_code": self.item_code, "qty": 10}],
                warehouse=self.own_warehouse,
            )

    def test_return_rejects_invoice_not_owned_by_caller(self) -> None:
        si_name = self._make_original_order(qty=2)
        frappe.set_user(self.other_van_user)
        with self.assertRaises(frappe.PermissionError):
            create_sales_return(
                client_id=f"test-return-{random_string(8)}",
                return_against=si_name,
                items=[{"item_code": self.item_code, "qty": 1}],
                warehouse=self.other_warehouse,
            )
