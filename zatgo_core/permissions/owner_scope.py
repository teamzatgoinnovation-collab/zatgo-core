"""Per-user DocTypes: a user sees and changes only their own rows.

`ZG Device Token` (push tokens) and `ZG User Preferences` grant every logged-in user read/write/create in
their DocType permissions, and the hub's own API checks ownership by hand -- but the generic REST API and
Desk list/form do not go through that API: any user could list, edit or register a token under someone
else (hijacking their notifications). These hooks make the rule hold on every route. System Manager and
Administrator see everything; the hub's own server code runs with `ignore_permissions` and is unaffected.

Hooks never return None for "no objection": Frappe reads a falsy return as a denial.
"""

from __future__ import annotations

import frappe

# DocType -> the field holding the owning user
OWNER_FIELD = {
    "ZG Device Token": "user",
    "ZG User Preferences": "user",
}


def _privileged(user: str) -> bool:
    return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def _conditions(doctype: str, user: str | None) -> str:
    user = user or frappe.session.user
    if _privileged(user):
        return ""
    return f"`tab{doctype}`.`{OWNER_FIELD[doctype]}` = {frappe.db.escape(user)}"


def _allowed(doctype: str, doc, user: str | None) -> bool:
    user = user or frappe.session.user
    if _privileged(user):
        return True
    return bool(user) and user != "Guest" and doc.get(OWNER_FIELD[doctype]) == user


def device_token_query(user=None):
    return _conditions("ZG Device Token", user)


def device_token_has_permission(doc, ptype=None, user=None):
    return _allowed("ZG Device Token", doc, user)


def user_preferences_query(user=None):
    return _conditions("ZG User Preferences", user)


def user_preferences_has_permission(doc, ptype=None, user=None):
    return _allowed("ZG User Preferences", doc, user)
