"""Validation for ZG Number Series Settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from frappe.model.document import Document


DEFAULT_DOCUMENT_TYPES = (
    "Sales Invoice",
    "Purchase Invoice",
    "POS Invoice",
    "Quotation",
    "Delivery Note",
    "Payment Entry",
    "Journal Entry",
    "Project",
    "Task",
    "Employee",
    "Customer",
    "Supplier",
    "Stock Entry",
    "Work Order",
    "Production",
)


def validate_number_series(doc: Document) -> None:
    """Ensure prefixes are unique and series rows are complete."""
    seen_doctypes: set[str] = set()
    seen_prefixes: set[str] = set()

    for row in doc.get("series_items") or []:
        if not row.document_type:
            frappe.throw(frappe._("Document Type is required on every series row"))
        if not row.prefix:
            frappe.throw(frappe._("Prefix is required on every series row"))
        key = row.document_type.strip()
        if key in seen_doctypes:
            frappe.throw(
                frappe._("Duplicate number series for document type {0}").format(key)
            )
        seen_doctypes.add(key)
        prefix = row.prefix.strip()
        if prefix in seen_prefixes:
            frappe.throw(frappe._("Duplicate prefix {0}").format(prefix))
        seen_prefixes.add(prefix)
        if int(row.padding or 0) < 1:
            frappe.throw(frappe._("Padding must be at least 1"))
