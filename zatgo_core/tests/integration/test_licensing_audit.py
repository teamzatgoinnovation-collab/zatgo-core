"""Audit trail rules (Phase 9): append-only, no forged entries, licensing entries kept; site_config changes seen."""

from __future__ import annotations

import json

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.licensing import audit, entitlement, watch


class TestAuditTrail(IntegrationTestCase):
    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.local.conf.pop(entitlement.CONF_KEY, None)

    def _entry(self, doctype: str = "Licence") -> str:
        audit.log("test_event", doctype, "X", {"a": 1})
        return frappe.get_last_doc("Audit Log", filters={"fieldname": "test_event", "doctype_name": doctype}).name

    def test_entries_cannot_be_changed(self) -> None:
        doc = frappe.get_doc("Audit Log", self._entry())
        doc.new_value = json.dumps({"a": 2})
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_entries_cannot_be_typed_in(self) -> None:
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({"doctype": "Audit Log", "doctype_name": "Licence", "fieldname": "forged",
                            "new_value": "{}"}).insert()

    def test_licensing_entries_cannot_be_deleted(self) -> None:
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("Audit Log", self._entry("Licence"), ignore_permissions=True)
        other = self._entry("Company Settings")
        frappe.delete_doc("Audit Log", other, ignore_permissions=True)  # the old rule for other entries
        self.assertFalse(frappe.db.exists("Audit Log", other))

    def test_site_config_changes_are_audited(self) -> None:
        watch.check()  # record the current state
        self.assertEqual(watch.check(), [])
        frappe.local.conf[entitlement.CONF_KEY] = 1
        self.assertEqual(watch.check(), ["enforcement"])
        row = frappe.get_last_doc("Audit Log", filters={"fieldname": "licence_config_changed"})
        self.assertEqual(json.loads(row.new_value), {"key": "enforcement", "from": 0, "to": 1})
        frappe.local.conf.pop(entitlement.CONF_KEY)
        self.assertEqual(watch.check(), ["enforcement"])
        snap = watch.snapshot()
        self.assertNotIn("issuer_key", json.dumps(snap).replace("issuer_key_configured", ""))
