"""Regression coverage for vansalex.aging leaking site-wide receivables.

aging.summary / aging.detail used to apply no caller scoping at all — a
Field User's dashboard received every open Sales Invoice on the site,
across every customer and company. Confirms a non-admin now only sees
customers on their own route (ZG Trip, the same rule create_collection
enforces) plus customers they invoiced themselves, is refused an explicit
out-of-scope customer, and that admins are unaffected.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1.vansalex.aging import detail, summary
from zatgo_core.services.vansalex_service import create_order
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestVansalexAgingScope(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.warehouse = cls._make_warehouse("VanSaleAgingTest")
        cls.item_code = cls._make_stocked_item(cls.warehouse, qty=1000)

    def setUp(self) -> None:
        # create_order() commits for real, so every test gets its own users
        # and customers rather than inheriting another test's invoices.
        self.van_user = self._make_van_user(self.warehouse)
        self.route_customer = self._make_customer(f"Aging Route {random_string(8)}")
        self.sold_customer = self._make_customer(f"Aging Sold {random_string(8)}")
        self.other_customer = self._make_customer(f"Aging Other {random_string(8)}")
        self._make_trip(self.van_user, self.route_customer)

        # Route customer: invoiced by someone else (admin) — still visible
        # to the driver, since collecting from them is theirs to do.
        self._make_invoice(self.route_customer)
        # Off-route customer the driver sold to themselves.
        frappe.set_user(self.van_user)
        self._make_invoice(self.sold_customer)
        frappe.set_user("Administrator")
        # Neither on the route nor invoiced by the driver.
        self._make_invoice(self.other_customer)

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
        code = f"VANSALE-AGING-{random_string(6).upper()}"
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
        email = f"vansale.aging.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "AgingTest",
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
    def _make_trip(cls, user: str, customer: str) -> None:
        frappe.get_doc(
            {
                "doctype": "ZG Trip",
                "title": "Aging Test Route",
                "customer": customer,
                "sequence": 1,
                "status": "Planned",
                "sales_user": user,
                "warehouse": cls.warehouse,
            }
        ).insert(ignore_permissions=True)

    def _make_invoice(self, customer: str) -> str:
        order = create_order(
            client_id=f"test-order-{random_string(8)}",
            customer=customer,
            items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
            warehouse=self.warehouse,
            company=self.company,
        )
        self.assertTrue(order["success"], order.get("error"))
        return order["data"]["erp_name"]

    @staticmethod
    def _summary_customers(result: dict) -> set[str]:
        return {c["customer"] for c in result["data"]["customers"]}

    # -- tests --------------------------------------------------------------

    def test_field_user_summary_only_covers_own_customers(self) -> None:
        frappe.set_user(self.van_user)
        seen = self._summary_customers(summary())
        self.assertEqual(seen, {self.route_customer, self.sold_customer})

    def test_field_user_detail_only_covers_own_customers(self) -> None:
        frappe.set_user(self.van_user)
        seen = {row["customer"] for row in detail(page_size=500)["data"]}
        self.assertEqual(seen, {self.route_customer, self.sold_customer})

    def test_field_user_is_refused_an_out_of_scope_customer(self) -> None:
        frappe.set_user(self.van_user)
        with self.assertRaises(frappe.PermissionError):
            summary(customer=self.other_customer)
        with self.assertRaises(frappe.PermissionError):
            detail(customer=self.other_customer)

    def test_field_user_can_filter_to_an_in_scope_customer(self) -> None:
        frappe.set_user(self.van_user)
        result = summary(customer=self.route_customer)
        self.assertEqual(self._summary_customers(result), {self.route_customer})

    def test_field_user_with_no_customers_sees_nothing(self) -> None:
        frappe.set_user(self._make_van_user(self.warehouse))
        result = summary()
        self.assertEqual(result["data"]["customers"], [])
        self.assertEqual(result["data"]["buckets"]["total"], 0)
        self.assertEqual(detail()["data"], [])

    def test_admin_still_sees_every_customer(self) -> None:
        for customer in (self.route_customer, self.sold_customer, self.other_customer):
            self.assertEqual(self._summary_customers(summary(customer=customer)), {customer})
