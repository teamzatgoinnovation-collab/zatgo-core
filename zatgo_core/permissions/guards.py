"""Permission guards for settings categories."""

from __future__ import annotations

import frappe

from zatgo_core.constants.roles import ROLE_PERMISSION_MATRIX, ROLES


def _user_roles() -> set[str]:
    return set(frappe.get_roles())


def can_access(category: str, *, write: bool = False) -> bool:
    """Return whether the current user may read/write a settings category."""
    roles = _user_roles()
    if ROLES["ADMINISTRATOR"] in roles or "Administrator" in roles:
        return True
    if ROLES["SYSTEM_MANAGER"] in roles:
        return True

    for role, matrix in ROLE_PERMISSION_MATRIX.items():
        if role not in roles:
            continue
        allowed = matrix.get(category, False)
        if not allowed:
            continue
        if write and role == ROLES["READ_ONLY"]:
            continue
        if write and category == "audit":
            # Audit is read-only for non system managers.
            if role != ROLES["SYSTEM_MANAGER"]:
                continue
        return True
    return False


def assert_can_read_settings(category: str) -> None:
    if not can_access(category, write=False):
        frappe.throw(
            frappe._("Not permitted to read {0} settings").format(category),
            frappe.PermissionError,
        )


def assert_can_write_settings(category: str) -> None:
    if not can_access(category, write=True):
        frappe.throw(
            frappe._("Not permitted to write {0} settings").format(category),
            frappe.PermissionError,
        )
