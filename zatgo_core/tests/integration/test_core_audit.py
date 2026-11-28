"""services/core/audit.py: the one Audit Log writer, and the three callers that go through it."""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string, today

from zatgo_core.licensing import audit as licence_audit
from zatgo_core.services.core import audit


def _rows(name: str) -> list[dict]:
    return frappe.get_all(
        "Audit Log",
        filters={"document_name": name},
        fields=["doctype_name", "fieldname", "old_value", "new_value", "changed_by", "change_date", "reason", "app_name"],
        order_by="creation asc",
    )


class TestCoreAudit(IntegrationTestCase):
    def setUp(self) -> None:
        self.name = f"AUDIT-TEST-{random_string(8)}"

    def test_record_writes_one_row(self) -> None:
        audit.record("Theme Settings", self.name, "primary_color", "#000000", "#2952E3", reason="rebrand")
        rows = _rows(self.name)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row.doctype_name, row.fieldname, row.old_value, row.new_value),
                         ("Theme Settings", "primary_color", "#000000", "#2952E3"))
        self.assertEqual((row.changed_by, str(row.change_date), row.reason, row.app_name),
                         (frappe.session.user, today(), "rebrand", "zatgo_core"))

    def test_values_are_stored_as_text(self) -> None:
        audit.record("Theme Settings", self.name, "max_users", 5, None)
        row = _rows(self.name)[0]
        self.assertEqual((row.old_value, row.new_value), ("5", None))

    def test_a_failed_write_is_logged_not_raised(self) -> None:
        with patch.object(frappe, "get_doc", side_effect=frappe.ValidationError("boom")):
            audit.record("Theme Settings", self.name, "x", 1, 2)  # does not raise
        self.assertEqual(_rows(self.name), [])

    def test_strict_lets_the_failure_raise(self) -> None:
        with patch.object(frappe, "get_doc", side_effect=frappe.ValidationError("boom")):
            with self.assertRaises(frappe.ValidationError):
                audit.record("Theme Settings", self.name, "x", 1, 2, strict=True)

    def test_licence_events_still_write_their_json_row(self) -> None:
        licence_audit.log("verify_failed", "Licence", self.name, {"licence_number": "L-1", "why": "bad signature"},
                          reason="bad signature")
        row = _rows(self.name)[0]
        self.assertEqual((row.doctype_name, row.fieldname, row.reason), ("Licence", "verify_failed", "bad signature"))
        self.assertEqual(json.loads(row.new_value), {"licence_number": "L-1", "why": "bad signature"})

    def test_settings_mixin_still_writes_changed_fields(self) -> None:
        doc = frappe.get_doc("Storage Settings")
        field = next(
            (df for df in doc.meta.fields if df.fieldtype in ("Data", "Int", "Select", "Check") and not df.read_only),
            None,
        )
        if field is None:
            self.skipTest("Storage Settings has no simple editable field")
        before = frappe.db.count("Audit Log", {"doctype_name": "Storage Settings", "fieldname": field.fieldname})
        old = doc.get(field.fieldname)
        try:
            if field.fieldtype == "Check":
                doc.set(field.fieldname, 0 if old else 1)
            elif field.fieldtype == "Int":
                doc.set(field.fieldname, (old or 0) + 1)
            elif field.fieldtype == "Select":
                options = [o for o in (field.options or "").split("\n") if o and o != old]
                if not options:
                    self.skipTest("no other option to choose")
                doc.set(field.fieldname, options[0])
            else:
                doc.set(field.fieldname, f"audit-{random_string(4)}")
            doc.save(ignore_permissions=True)
            after = frappe.db.count("Audit Log", {"doctype_name": "Storage Settings", "fieldname": field.fieldname})
            self.assertEqual(after, before + 1)
        finally:
            frappe.db.rollback()
