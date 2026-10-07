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
            "Sales Invoice",
            return_name,
            ["is_return", "docstatus", "grand_total", "return_against", "naming_series"],
            as_dict=True,
        )
        self.assertEqual(return_doc.is_return, 1)
        self.assertIn(
            "RET-",
            return_doc.naming_series,
            "Return must use the site's configured return naming series, not the plain invoice one "
            "(regression test for kasibasia's SINV-00008, which continued the plain SINV- counter)",
        )
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

    def test_returnable_nets_out_earlier_returns(self) -> None:
        from zatgo_core.services.vansalex_service import get_returnable

        si_name = self._make_original_order(qty=5)
        create_sales_return(
            client_id=f"test-return-{random_string(8)}",
            return_against=si_name,
            items=[{"item_code": self.item_code, "qty": 2}],
            warehouse=self.own_warehouse,
        )
        line = get_returnable(si_name)["items"][0]
        self.assertEqual((line["sold_qty"], line["returned_qty"], line["returnable_qty"]), (5, 2, 3))
        # A second return may only take what is left.
        with self.assertRaises(frappe.ValidationError):
            create_sales_return(
                client_id=f"test-return-{random_string(8)}",
                return_against=si_name,
                items=[{"item_code": self.item_code, "qty": 4}],
                warehouse=self.own_warehouse,
            )

    def test_partial_return_of_item_on_two_lines_credits_requested_qty_once(self) -> None:
        # The same item on two invoice lines: returning 3 must credit 3 in
        # total, not 3 on every line carrying that item (which credited 6).
        # Two lines of one item need Selling Settings to allow it.
        with self.change_settings("Selling Settings", allow_multiple_items=1, commit=True):
            self._check_two_line_return()

    def _check_two_line_return(self) -> None:
        order = create_order(
            client_id=f"test-return-order-{random_string(8)}",
            customer=self.own_customer,
            items=[
                {"item_code": self.item_code, "qty": 2, "rate": 10},
                {"item_code": self.item_code, "qty": 5, "rate": 10},
            ],
            warehouse=self.own_warehouse,
            company=self.company,
        )
        self.assertTrue(order["success"], order.get("error"))
        si_name = order["data"]["erp_name"]
        self.assertEqual(len(frappe.get_doc("Sales Invoice", si_name).items), 2)

        result = create_sales_return(
            client_id=f"test-return-{random_string(8)}",
            return_against=si_name,
            items=[{"item_code": self.item_code, "qty": 3}],
            warehouse=self.own_warehouse,
        )
        self.assertTrue(result["success"], result.get("error"))
        ret = frappe.get_doc("Sales Invoice", result["data"]["erp_name"])
        self.assertEqual(sum(row.qty for row in ret.items), -3)
        self.assertEqual(ret.net_total, -30)
        # Filled line by line, never past what a line has left to return.
        self.assertEqual([row.qty for row in ret.items], [-2, -1])

    def test_van_user_returns_own_sale_into_default_warehouse(self) -> None:
        si_name = self._make_original_order(qty=3)
        frappe.db.set_value("Sales Invoice", si_name, "owner", self.van_user)
        frappe.set_user(self.van_user)
        result = create_sales_return(
            client_id=f"test-return-{random_string(8)}",
            return_against=si_name,
            items=[{"item_code": self.item_code, "qty": 1}],
        )
        self.assertTrue(result["success"], result.get("error"))
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", result["data"]["erp_name"], "set_warehouse"),
            self.own_warehouse,
        )

