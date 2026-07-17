"""Validation for ZG Branch Settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from frappe.model.document import Document


def validate_branch_settings(doc: Document) -> None:
    """Validate branch identity and warehouse ownership."""
    if not doc.branch_name:
        frappe.throw(frappe._("Branch Name is required"))
    if not doc.company:
        frappe.throw(frappe._("Company is required"))

    duplicates = frappe.db.exists(
        "ZG Branch Settings",
        {
            "branch_name": doc.branch_name,
            "company": doc.company,
            "name": ("!=", doc.name),
        },
    )
    if duplicates:
        frappe.throw(
            frappe._("Branch {0} already exists for company {1}").format(
                doc.branch_name, doc.company
            )
        )

    if doc.warehouse:
        warehouse_company = frappe.db.get_value("Warehouse", doc.warehouse, "company")
        if warehouse_company and warehouse_company != doc.company:
            frappe.throw(frappe._("Warehouse must belong to the selected Company"))
