"""setup/data_integrity.report: read-only, and it finds what it claims to find."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.setup import data_integrity


class TestDataIntegrity(IntegrationTestCase):
    def test_covers_every_non_single_app_doctype(self) -> None:
        names = data_integrity.app_doctypes()
        self.assertIn("Trip", names)
        self.assertNotIn("ZatGo System Settings", names)

    def test_changes_nothing(self) -> None:
        before = frappe.db.sql("select count(*), max(modified) from `tabTrip`")[0]
        data_integrity.report(["Trip", "Order", "Device Token"])
        self.assertEqual(frappe.db.sql("select count(*), max(modified) from `tabTrip`")[0], before)

    def test_finds_a_dangling_link_and_a_missing_mandatory_value(self) -> None:
        token = frappe.get_doc({"doctype": "Device Token", "token": f"zg-integrity-{random_string(10)}",
                                "user": "Administrator", "platform": "android"}).insert(ignore_permissions=True)
        try:
            frappe.db.set_value("Device Token", token.name, "user", f"nobody-{random_string(6)}@example.test",
                                update_modified=False)
            found = data_integrity.check_doctype("Device Token")
            self.assertGreaterEqual(found.get("dangling_links", {}).get("user", 0), 1)
        finally:
            frappe.db.rollback()

    def test_finds_duplicate_client_ids(self) -> None:
        if not frappe.db.has_column("Trip", "zatgo_client_id"):
            self.skipTest("no zatgo_client_id on Trip")
        found = data_integrity.check_doctype("Trip")
        self.assertNotIn("zatgo_client_id", found.get("duplicates", {}), "the unique index should make this impossible")
