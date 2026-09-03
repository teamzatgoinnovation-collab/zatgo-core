"""Route-plan stop creation, idempotency, reordering and row-level access.

The mobile client creates ZG Trip stops offline and retries on reconnect, so
`create_trip` has to behave exactly like the other client-generated writes:
the same `client_id` twice must resolve to one document, never two stops on
the salesperson's route.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string, today

from zatgo_core.services.vansalex_service import (
    create_trip,
    reorder_trips,
    update_visit,
)


class TestVanSaleXTrips(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.customer = f"TripTest-{random_string(6).upper()}"
        if not frappe.db.exists("Customer", cls.customer):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": cls.customer,
                    "customer_group": frappe.db.get_value(
                        "Customer Group", {"is_group": 0}, "name"
                    ),
                    "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
                }
            ).insert(ignore_permissions=True)

    def setUp(self) -> None:
        frappe.set_user("Administrator")

    def _create(self, client_id: str, **kwargs):
        return create_trip(
            client_id=client_id,
            customer=self.customer,
            planned_at=today(),
            **kwargs,
        )

    def test_create_returns_trip(self) -> None:
        cid = f"trip-{random_string(10)}"
        res = self._create(cid, address="12 Test Street", sequence=1)
        self.assertTrue(res["success"])
        self.assertTrue(res["meta"]["created"])
        self.assertEqual(res["data"]["customer"], self.customer)
        self.assertEqual(res["data"]["status"], "Planned")
        self.assertEqual(res["data"]["sequence"], 1)
        self.assertTrue(frappe.db.exists("ZG Trip", res["data"]["name"]))

    def test_duplicate_client_id_is_idempotent(self) -> None:
        cid = f"trip-{random_string(10)}"
        first = self._create(cid, sequence=1)
        second = self._create(cid, sequence=9)

        self.assertEqual(first["data"]["name"], second["data"]["name"])
        self.assertTrue(second["meta"]["idempotent"])
        # The idempotent-duplicate branch omits "created" rather than setting
        # it False, matching every other create_* function in this codebase.
        self.assertFalse(second["meta"].get("created"))
        # The retry must not have created a second stop, nor moved the first.
        rows = frappe.get_all("ZG Trip", filters={"zatgo_client_id": cid}, pluck="name")
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            frappe.db.get_value("ZG Trip", first["data"]["name"], "sequence"), 1
        )

    def test_visit_update_preserves_create_client_id(self) -> None:
        """A check-in must not overwrite the stop's create idempotency key."""
        cid = f"trip-{random_string(10)}"
        created = self._create(cid)
        name = created["data"]["name"]

        update_visit(
            client_id=f"visit-{random_string(10)}",
            stop_id=name,
            visit_status="Checked In",
            lat=24.7136,
            lng=46.6753,
        )

        self.assertEqual(frappe.db.get_value("ZG Trip", name, "zatgo_client_id"), cid)
        self.assertEqual(frappe.db.get_value("ZG Trip", name, "status"), "Checked In")
        # And the create is still idempotent afterwards.
        again = self._create(cid)
        self.assertEqual(again["data"]["name"], name)
        self.assertFalse(again["meta"].get("created"))

    def test_reorder_writes_sequences(self) -> None:
        a = self._create(f"trip-{random_string(10)}", sequence=1)["data"]["name"]
        b = self._create(f"trip-{random_string(10)}", sequence=2)["data"]["name"]

        res = reorder_trips([{"name": b, "sequence": 1}, {"name": a, "sequence": 2}])

        self.assertTrue(res["success"])
        self.assertEqual(res["meta"]["updated"], 2)
        self.assertEqual(frappe.db.get_value("ZG Trip", b, "sequence"), 1)
        self.assertEqual(frappe.db.get_value("ZG Trip", a, "sequence"), 2)

    def test_client_id_column_is_unique(self) -> None:
        """The DB constraint insert_idempotent relies on must really exist."""
        rows = frappe.db.sql(
            """
            SELECT INDEX_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'tabZG Trip'
              AND COLUMN_NAME = 'zatgo_client_id'
              AND NON_UNIQUE = 0
            """,
            as_dict=True,
        )
        self.assertTrue(rows, "ZG Trip.zatgo_client_id has no UNIQUE index")
