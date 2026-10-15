"""Industry roles must exist before DocType sync: the industries' DocTypes
list them in their permissions."""

from __future__ import annotations

import frappe

from zatgo_core.industries.registry import INDUSTRIES


def execute() -> None:
    for ind in INDUSTRIES.values():
        for role in ind.roles:
            if not frappe.db.exists("Role", role):
                frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                    ignore_permissions=True
                )
