"""Modern print formats for Balance Sheet / Profit and Loss Statement / Trial Balance."""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from zatgo_core.setup.ensure_report_print_formats import FORMATS, ensure_report_print_formats


class TestReportPrintFormats(IntegrationTestCase):
    def test_creates_one_js_format_per_report_and_is_idempotent(self) -> None:
        ensure_report_print_formats()
        ensure_report_print_formats()
        for report, name in FORMATS.items():
            if not frappe.db.exists("Report", report):
                continue
            doc = frappe.get_doc("Print Format", name)
            self.assertEqual(doc.print_format_for, "Report")
            self.assertEqual(doc.report, report)
            self.assertEqual(doc.print_format_type, "JS")
            self.assertFalse(doc.disabled)
            self.assertIn("zgfs-table", doc.html)
            self.assertEqual(frappe.db.count("Print Format", {"name": name}), 1)
