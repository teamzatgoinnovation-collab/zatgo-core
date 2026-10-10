"""Company / branch scoped permission query helpers.

Wire into hooks.permission_query_conditions when DocTypes include company/branch.
"""

from __future__ import annotations

import frappe


def company_query_for(doctype: str, user: str | None = None) -> str:
    """Restrict list queries to companies allowed for the user.

    Returns an empty string for Administrator / System Manager so they see all.
    Callers should bind this per DocType, e.g.:

        permission_query_conditions = {
            "My Doc": "zatgo_core.zatgo_space.permissions.company_scope.query_my_doc",
        }
    """
    user = user or frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    companies = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Company"},
        pluck="for_value",
    )
    if not companies:
        # No explicit user permissions: defer to role permissions only.
        return ""

    escaped = ", ".join(frappe.db.escape(c) for c in companies)
    return f"`tab{doctype}`.company in ({escaped})"
