"""api/v1/sync/batch: a failing op leaves nothing behind."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1.sync.batch import batch


def _mobile() -> str:
    # Mobile numbers are unique per customer, and batch() commits for real.
    import random

    return f"+9665{random.randint(10_000_000, 99_999_999)}"


class TestSyncBatch(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")

    def _create(self) -> tuple[str, str]:
        cid = f"test-batch-{random_string(8)}"
        res = batch(
            [
                {
                    "id": "1",
                    "entity_type": "customer",
                    "op": "create",
                    "client_id": cid,
                    "payload": {
                        "customer_name": f"Batch Test {random_string(6)}",
                        "mobile_no": _mobile(),
                        "address_line1": "King Fahd Road",
                        "city": "Riyadh",
                        "country": "Saudi Arabia",
                    },
                }
            ]
        )
        result = res["data"]["results"][0]
        self.assertTrue(result["success"], result)
        name = frappe.db.get_value("Customer", {"zatgo_client_id": cid}, "name")
        self.assertTrue(name)
        return cid, name

    def test_failed_op_is_rolled_back_and_the_next_op_still_runs(self) -> None:
        cid, name = self._create()
        original = frappe.db.get_value("Customer", name, "customer_name")
        other_cid, other = self._create()

        # The update saves the Customer, then fails on its contact / address:
        # the half-done save must not be committed by the next op.
        with patch(
            "zatgo_core.services.customer_sync_ops._sync_contact_address",
            side_effect=[frappe.ValidationError("boom"), None],
        ):
            res = batch(
                [
                    {
                        "id": "a",
                        "entity_type": "customer",
                        "op": "update",
                        "client_id": cid,
                        "force": 1,
                        "payload": {"customer_name": "Changed Then Failed", "mobile_no": _mobile(), "address_line1": "King Fahd Road", "city": "Riyadh", "country": "Saudi Arabia"},
                    },
                    {
                        "id": "b",
                        "entity_type": "customer",
                        "op": "update",
                        "client_id": other_cid,
                        "force": 1,
                        "payload": {"customer_name": f"Updated {random_string(5)}", "mobile_no": _mobile(), "address_line1": "King Fahd Road", "city": "Riyadh", "country": "Saudi Arabia"},
                    },
                ]
            )
        first, second = res["data"]["results"]
        self.assertFalse(first["success"])
        self.assertEqual(first["error"], "boom", "op a must fail after its save, not in validation")
        self.assertTrue(second["success"], second)
        self.assertEqual(frappe.db.get_value("Customer", name, "customer_name"), original)
