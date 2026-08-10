"""Shared VanSale role / profile helpers for go_van APIs."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.constants.roles import ROLES


ROLE_USER = ROLES["VANSALE_USER"]
ROLE_ADMIN = ROLES["VANSALE_ADMIN"]


def user_roles(user: str | None = None) -> list[str]:
    return list(frappe.get_roles(user or frappe.session.user))


def is_vansale_admin(user: str | None = None) -> bool:
    roles = set(user_roles(user))
    return (
        ROLE_ADMIN in roles
        or "System Manager" in roles
        or "Administrator" in roles
        or (user or frappe.session.user) == "Administrator"
    )


def is_vansale_user(user: str | None = None) -> bool:
    return ROLE_USER in set(user_roles(user))


def get_profile(user: str | None = None) -> dict[str, Any] | None:
    uid = user or frappe.session.user
    if not frappe.db.exists("DocType", "ZG Van Sale Profile"):
        return None
    name = frappe.db.get_value(
        "ZG Van Sale Profile",
        {"user": uid, "enabled": 1},
        "name",
    )
    if not name:
        return None
    doc = frappe.get_doc("ZG Van Sale Profile", name)
    series = ""
    if hasattr(doc, "sales_invoice_naming_series"):
        series = (doc.sales_invoice_naming_series or "").strip()
    return_series = ""
    if hasattr(doc, "sales_return_naming_series"):
        return_series = (doc.sales_return_naming_series or "").strip()
    return {
        "id": doc.name,
        "user": doc.user,
        "warehouse": doc.warehouse,
        "vehicle": doc.vehicle,
        "route_title": doc.route_title,
        "enabled": int(doc.enabled or 0),
        "notes": doc.notes or "",
        "sales_invoice_naming_series": series,
        "sales_return_naming_series": return_series,
        "user_type": getattr(doc, "user_type", None) or "Field User",
    }


def require_own_warehouse(requested: str | None = None) -> str:
    """Resolve the warehouse a non-admin caller may act on.

    Admins may pass any warehouse (or none). Non-admins must have a
    warehouse on their VanSale profile, and may not request a different
    one — this is the single source of truth for the "can this caller
    touch this warehouse" check used across go_van stock/orders/collections.
    """
    wh = (requested or "").strip()
    if is_vansale_admin():
        return wh
    profile = get_profile()
    user_wh = (profile.get("warehouse") if profile else "") or ""
    if not user_wh:
        frappe.throw("No van warehouse assigned to your profile.", frappe.ValidationError)
    if wh and wh != user_wh:
        frappe.throw(
            "Access denied: You can only act on your assigned warehouse.",
            frappe.PermissionError,
        )
    return user_wh


def map_profile_row(row: Any) -> dict[str, Any]:
    r = row.as_dict() if callable(getattr(row, "as_dict", None)) else dict(row)
    full_name = frappe.db.get_value("User", r.get("user"), "full_name") or r.get("user")
    return {
        "id": r.get("name"),
        "user": r.get("user"),
        "full_name": full_name,
        "warehouse": r.get("warehouse"),
        "vehicle": r.get("vehicle"),
        "route_title": r.get("route_title") or "",
        "enabled": int(r.get("enabled") or 0),
    }
