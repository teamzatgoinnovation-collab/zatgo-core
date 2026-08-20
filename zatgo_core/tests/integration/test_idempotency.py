"""Idempotency coverage for zatgo_client_id-keyed document creation.

Two concerns, tested separately:

1. The ordinary pre-check path (client_id already exists -> return it) —
   already implicitly exercised elsewhere, made explicit here.
2. The race-recovery path in `insert_idempotent`: a concurrent request can
   win the create between this request's pre-check and its own `insert()`,
   which must be recovered as an idempotent ack, not a raw error, and must
   never result in two documents sharing one client_id.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.services.vansalex_service import create_order
from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent


class TestIdempotency(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = frappe.db.get_value("Company", {}, "name")
        if not cls.company:
            frappe.throw("No Company found — run install_fixtures before this test.")
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        cls.warehouse = f"IdempotencyTest - {abbr}" if abbr else "IdempotencyTest"
        if not frappe.db.exists("Warehouse", cls.warehouse):
            frappe.get_doc(
                {
                    "doctype": "Warehouse",
                    "warehouse_name": "IdempotencyTest",
                    "company": cls.company,
                }
            ).insert(ignore_permissions=True)
        cls.item_code = f"IDEMPOTENCY-TEST-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": cls.item_code,
                "item_name": cls.item_code,
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
                        "item_code": cls.item_code,
                        "qty": 100,
                        "t_warehouse": cls.warehouse,
                        "basic_rate": 10,
                    }
                ],
            }
        ).insert(ignore_permissions=True).submit()
        cls.customer = "Idempotency Test Customer"
        if not frappe.db.exists("Customer", cls.customer):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": cls.customer,
                    "customer_type": "Individual",
                    "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                    "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
                }
            ).insert(ignore_permissions=True)

    def setUp(self) -> None:
        frappe.set_user("Administrator")

    # -- zatgo_client_id schema itself --------------------------------------

    def test_zatgo_client_id_has_unique_db_constraint(self) -> None:
        """Regression guard for the "patch recorded as run but field never
        materialized" incident: this must actually be a unique index on the
        live table, not just a Custom Field record."""
        self.assertTrue(frappe.db.has_column("Sales Invoice", "zatgo_client_id"))
        self.assertTrue(frappe.db.has_column("Payment Entry", "zatgo_client_id"))
        self.assertTrue(frappe.db.has_column("Stock Entry", "zatgo_client_id"))
        for doctype in ("Sales Invoice", "Payment Entry", "Stock Entry"):
            rows = frappe.db.sql(
                """
                SELECT NON_UNIQUE FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND COLUMN_NAME = 'zatgo_client_id'
                """,
                (f"tab{doctype}",),
            )
            self.assertTrue(rows, f"No index at all on {doctype}.zatgo_client_id")
            self.assertEqual(rows[0][0], 0, f"{doctype}.zatgo_client_id index is not UNIQUE")

    # -- ordinary pre-check idempotency --------------------------------------

    def test_create_order_same_client_id_twice_returns_same_invoice(self) -> None:
        cid = f"idem-test-{random_string(8)}"
        first = create_order(
            client_id=cid,
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
            warehouse=self.warehouse,
        )
        self.assertTrue(first["success"], first.get("error"))
        second = create_order(
            client_id=cid,
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": 1, "rate": 10}],
            warehouse=self.warehouse,
        )
        self.assertTrue(second["success"], second.get("error"))
        self.assertEqual(first["data"]["erp_name"], second["data"]["erp_name"])
        self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid}), 1)

    # -- the actual race: concurrent insert, not a pre-check hit -------------

    def test_insert_idempotent_recovers_from_concurrent_duplicate(self) -> None:
        """Simulates two requests racing past the pre-check: build and insert
        the "winner" directly (bypassing create_order's own pre-check), then
        make insert_idempotent try to insert a second, different in-memory
        doc with the same client_id — as if this request's pre-check had run
        a moment before the winner committed. It must recover cleanly."""
        cid = f"idem-race-{random_string(8)}"

        winner = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": self.customer,
                "company": self.company,
                "posting_date": frappe.utils.today(),
                "items": [{"item_code": self.item_code, "qty": 1, "rate": 10}],
                "zatgo_client_id": cid,
                "update_stock": 1,
                "set_warehouse": self.warehouse,
            }
        )
        winner.insert(ignore_permissions=True)
        winner.submit()
        frappe.db.commit()

        loser = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": self.customer,
                "company": self.company,
                "posting_date": frappe.utils.today(),
                "items": [{"item_code": self.item_code, "qty": 1, "rate": 10}],
                "zatgo_client_id": cid,
                "update_stock": 1,
                "set_warehouse": self.warehouse,
            }
        )

        recovered_doc, created = insert_idempotent(loser, doctype="Sales Invoice", client_id=cid)

        self.assertFalse(created)
        self.assertEqual(recovered_doc.name, winner.name)
        self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid}), 1)
        # The loser's in-memory doc must never have been persisted under its
        # own identity — only the winner's document exists.
        self.assertEqual(find_by_client_id("Sales Invoice", cid), winner.name)
