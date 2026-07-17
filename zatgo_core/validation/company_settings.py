"""Validation for ZG Company Settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from frappe.model.document import Document


def validate_company_settings(doc: Document) -> None:
    """Ensure company uniqueness and linked references are valid."""
    if not doc.company:
        frappe.throw(frappe._("Company is required"))

    if frappe.db.exists("ZG Company Settings", {"company": doc.company, "name": ("!=", doc.name)}):
        frappe.throw(
            frappe._("Company Settings already exist for {0}").format(doc.company)
        )

    if doc.default_warehouse:
        warehouse_company = frappe.db.get_value("Warehouse", doc.default_warehouse, "company")
        if warehouse_company and warehouse_company != doc.company:
            frappe.throw(frappe._("Default Warehouse must belong to the selected Company"))

    if doc.default_cost_center:
        cc_company = frappe.db.get_value("Cost Center", doc.default_cost_center, "company")
        if cc_company and cc_company != doc.company:
            frappe.throw(frappe._("Default Cost Center must belong to the selected Company"))
