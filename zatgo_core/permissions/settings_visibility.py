"""Role-based visibility for registered applications and sections."""

from __future__ import annotations

import frappe

from zatgo_core.constants.roles import ROLES


def _parse_roles(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part and part.strip()}


def user_roles(user: str | None = None) -> set[str]:
    return set(frappe.get_roles(user or frappe.session.user))


def is_superuser(roles: set[str] | None = None) -> bool:
    roles = roles or user_roles()
    return bool(
        roles
        & {
            "Administrator",
            ROLES["ADMINISTRATOR"],
            ROLES["SYSTEM_MANAGER"],
            "System Manager",
        }
    )


def can_see_roles(allowed_csv: str | None, roles: set[str] | None = None) -> bool:
    """True if user may see a resource given optional allowed roles CSV."""
    roles = roles or user_roles()
    if is_superuser(roles):
        return True
    if ROLES["APPLICATION_ADMIN"] in roles or "ZG Application Admin" in roles:
        return True
    allowed = _parse_roles(allowed_csv)
    if not allowed:
        return True
    return bool(roles & allowed)


def can_manage_registry() -> bool:
    roles = user_roles()
    return is_superuser(roles) or ROLES["APPLICATION_ADMIN"] in roles
