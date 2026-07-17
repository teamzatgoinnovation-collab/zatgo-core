"""Company-scoped permission query helpers."""

from __future__ import annotations

import frappe


def company_permission_query(user: str | None = None) -> str:
    """Restrict ZG Company Settings to companies the user can access."""
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user) or user == "Administrator":
        return ""
    companies = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Company"},
        pluck="for_value",
    )
    if not companies:
        return ""
    escaped = ", ".join(frappe.db.escape(c) for c in companies)
    return f"`tabZG Company Settings`.company in ({escaped})"
