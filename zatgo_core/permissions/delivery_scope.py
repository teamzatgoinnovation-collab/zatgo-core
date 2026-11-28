"""A courier sees and changes only their own delivery stops, on every route (Desk, REST, lists, reports, the API).

A courier is a user linked to a Delivery Boy. Managers (MANAGER_ROLES) and other staff, such as dispatchers, are not
restricted here: their role permissions decide. The delivery API applies the same rule before any change
(api/v1/delivery/stops._assert_own_stop).
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.constants.roles import ROLES

DOCTYPE = "ZatGo Delivery Stop"
MANAGER_ROLES = frozenset({ROLES["SYSTEM_MANAGER"], ROLES["COMPANY_ADMIN"], ROLES["BRANCH_ADMIN"]})


def is_manager(user: str | None = None) -> bool:
    return bool(MANAGER_ROLES.intersection(frappe.get_roles(user)))


def courier_of(user: str | None = None) -> str | None:
    """The Delivery Boy linked to `user`, if they are a courier."""
    user = user or frappe.session.user
    if user in ("Administrator", "Guest") or not frappe.db.exists("DocType", "Delivery Boy"):
        return None
    return frappe.db.get_value("Delivery Boy", {"user": user}, "name")


def stop_has_permission(doc: Any = None, ptype: str | None = None, user: str | None = None, **kwargs: Any) -> bool:
    """has_permission for ZatGo Delivery Stop: a courier only on their own stops. True/False, never None."""
    user = user or frappe.session.user
    if user == "Administrator" or is_manager(user):
        return True
    boy = courier_of(user)
    if not boy or doc is None or isinstance(doc, str):
        return True
    return (doc.get("delivery_boy") if hasattr(doc, "get") else None) == boy


def stop_query(user: str | None = None, **kwargs: Any) -> str:
    """permission_query_conditions: a courier's lists, reports and exports hold only their own stops."""
    user = user or frappe.session.user
    if user == "Administrator" or is_manager(user):
        return ""
    boy = courier_of(user)
    if not boy:
        return ""
    return f"`tab{DOCTYPE}`.`delivery_boy` = {frappe.db.escape(boy)}"
