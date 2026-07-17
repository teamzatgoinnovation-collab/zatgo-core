"""Validation for ZG Application Registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from frappe.model.document import Document


def validate_app_registry(doc: Document) -> None:
    """Validate app name and declared dependencies."""
    if not doc.app_name:
        frappe.throw(frappe._("App Name is required"))

    if " " in (doc.app_name or ""):
        frappe.throw(frappe._("App Name must be a Frappe app package name (snake_case)"))

    depends = [
        part.strip()
        for part in (doc.depends_on or "").split(",")
        if part and part.strip()
    ]
    for dep in depends:
        if dep == doc.app_name:
            frappe.throw(frappe._("App cannot depend on itself"))
        if not frappe.db.exists("ZG Application Registry", dep):
            # Soft warning via message — hard fail only when dependency is marked installed.
            status = frappe.db.get_value("ZG Application Registry", dep, "app_status")
            if status == "Installed":
                continue
            frappe.msgprint(
                frappe._("Dependency {0} is not registered yet").format(dep),
                indicator="orange",
                alert=True,
            )
