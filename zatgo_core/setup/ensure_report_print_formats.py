"""Modern print formats for the three financial statements.

Balance Sheet, Profit and Loss Statement and Trial Balance all print through one client-side
template (print_formats/financial_statement/). They are Print Formats of type JS for a Report, so
they appear in the report's Print / PDF dialog, and public/saas_theme/js/saas_theme.js makes the
Print / PDF default to them when no format is picked. Idempotent; run on install and migrate.
"""

from __future__ import annotations

import os

import frappe

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "print_formats", "financial_statement")

# report -> Print Format name
FORMATS = {
    "Balance Sheet": "ZG Balance Sheet",
    "Profit and Loss Statement": "ZG Profit and Loss Statement",
    "Trial Balance": "ZG Trial Balance",
}


def _read(name: str) -> str:
    with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as f:
        return f.read()


def ensure_report_print_formats() -> None:
    html, css = _read("financial_statement.html"), _read("financial_statement.css")
    for report, name in FORMATS.items():
        if not frappe.db.exists("Report", report):
            continue
        if frappe.db.exists("Print Format", name):
            doc = frappe.get_doc("Print Format", name)
        else:
            doc = frappe.new_doc("Print Format")
            doc.name = name
        doc.print_format_for = "Report"
        doc.report = report
        doc.print_format_type = "JS"
        doc.custom_format = 1
        doc.standard = "No"
        doc.module = "ZatGo Core"
        doc.disabled = 0
        doc.html = html
        doc.css = css
        if doc.is_new():
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)
