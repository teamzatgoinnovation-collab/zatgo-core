"""Shared VanSale role / profile helpers for go_van APIs."""

from __future__ import annotations

from typing import Any

import frappe

def user_roles(user: str | None = None) -> list[str]:
    return list(frappe.get_roles(user or frappe.session.user))


def is_vansale_admin(user: str | None = None) -> bool:
    roles = set(user_roles(user))
    return (
        "System Manager" in roles
        or "Administrator" in roles
        or "ZG Company Admin" in roles
        or (user or frappe.session.user) == "Administrator"
    )


def is_vansale_user(user: str | None = None) -> bool:
    uid = user or frappe.session.user
    return bool(uid and uid != "Guest")


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
    return {
        "id": doc.name,
        "user": doc.user,
        "warehouse": doc.warehouse,
        "vehicle": doc.vehicle,
        "route_title": doc.route_title,
        "enabled": int(doc.enabled or 0),
        "notes": doc.notes or "",
    }


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
