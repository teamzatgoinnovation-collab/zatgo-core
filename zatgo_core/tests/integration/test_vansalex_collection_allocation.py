"""Regression coverage for BUG-003 (QA audit): create_collection() used to
always target a single invoice — the most recently posted one — no matter
how many invoices a customer had open, or how large the collected amount
was relative to that one invoice. A driver collecting a customer's full
displayed outstanding (the sum across every open invoice) would silently
misallocate or get hard-rejected the moment it exceeded that single
newest invoice's own outstanding.

Confirms the fix: with no sales_invoice specified, a collection now
allocates oldest-invoice-first across as many open invoices as the amount
covers, and an amount spanning every open invoice clears all of them.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.services.vansalex_service import create_collection, create_order
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestVansalexCollectionAllocation(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.warehouse = cls._make_warehouse("VanSaleAllocTest")
        cls.item_code = cls._make_stocked_item(cls.warehouse, qty=1000)
        cls.van_user = cls._make_van_user(cls.warehouse)

    def setUp(self) -> None:
        # create_order()/create_collection() both commit for real (they
        # post genuine submitted documents) — normal per-test transaction
        # rollback does NOT undo that, so a customer shared across test
        # methods would carry leftover open/partially-paid invoices from
        # whichever test ran first. Give every test its own customer.
        self.customer = self._make_customer(f"VanSale Alloc Test {random_string(8)}")
        self._make_trip(self.van_user, self.customer, self.warehouse)
        frappe.set_user(self.van_user)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    # -- fixtures (mirrors test_vansalex_order_to_payment.py) -------------

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
        code = f"VANSALE-ALLOC-{random_string(6).upper()}"
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
        email = f"vansale.alloc.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "VanSale",
                "last_name": "AllocTest",
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
                "title": "Alloc Test Route",
                "customer": customer,
                "sequence": 1,
                "status": "Planned",
                "sales_user": user,
                "warehouse": warehouse,
            }
        ).insert(ignore_permissions=True)

    def _make_invoice(self, qty: float) -> tuple[str, float]:
        order = create_order(
            client_id=f"test-order-{random_string(8)}",
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": qty, "rate": 10}],
            warehouse=self.warehouse,
            company=self.company,
        )
        self.assertTrue(order["success"], order.get("error"))
        si_name = order["data"]["erp_name"]
        outstanding = frappe.db.get_value("Sales Invoice", si_name, "outstanding_amount")
        return si_name, outstanding

    # -- tests --------------------------------------------------------------

    def test_collection_covering_two_invoices_clears_both_oldest_first(self) -> None:
        older_si, older_outstanding = self._make_invoice(qty=1)  # SAR 10
        newer_si, newer_outstanding = self._make_invoice(qty=2)  # SAR 20
        total = older_outstanding + newer_outstanding

        collection = create_collection(
            client_id=f"test-collect-{random_string(8)}",
            customer=self.customer,
            amount=total,
        )
        self.assertTrue(collection["success"], collection.get("error"))

        self.assertEqual(
            frappe.db.get_value("Sales Invoice", older_si, "outstanding_amount"), 0
        )
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", newer_si, "outstanding_amount"), 0
        )

    def test_partial_collection_hits_oldest_invoice_first(self) -> None:
        older_si, older_outstanding = self._make_invoice(qty=1)  # SAR 10
        newer_si, newer_outstanding = self._make_invoice(qty=3)  # SAR 30

        # Collect exactly enough to clear the older invoice and nothing else.
        collection = create_collection(
            client_id=f"test-collect-{random_string(8)}",
            customer=self.customer,
            amount=older_outstanding,
        )
        self.assertTrue(collection["success"], collection.get("error"))

        self.assertEqual(
            frappe.db.get_value("Sales Invoice", older_si, "outstanding_amount"), 0
        )
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", newer_si, "outstanding_amount"),
            newer_outstanding,
            "the newer invoice must be untouched — the older one is paid first",
        )

    def test_collection_spanning_into_second_invoice_splits_correctly(self) -> None:
        older_si, older_outstanding = self._make_invoice(qty=1)  # SAR 10
        newer_si, newer_outstanding = self._make_invoice(qty=3)  # SAR 30

        # Fully clear the older invoice plus a partial amount of the newer one.
        partial_on_newer = 12.0
        collection = create_collection(
            client_id=f"test-collect-{random_string(8)}",
            customer=self.customer,
            amount=older_outstanding + partial_on_newer,
        )
        self.assertTrue(collection["success"], collection.get("error"))

        self.assertEqual(
            frappe.db.get_value("Sales Invoice", older_si, "outstanding_amount"), 0
        )
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", newer_si, "outstanding_amount"),
            newer_outstanding - partial_on_newer,
        )
