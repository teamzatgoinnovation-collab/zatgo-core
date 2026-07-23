"""Ensure ZatGo Core enterprise roles exist."""

from __future__ import annotations

import frappe

from zatgo_core.constants.roles import ROLES
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

CORE_ROLES = (
    ROLES["COMPANY_ADMIN"],
    ROLES["BRANCH_ADMIN"],
    ROLES["APPLICATION_ADMIN"],
    ROLES["READ_ONLY"],
    ROLES["DELIVERY"],
)


def ensure_roles() -> None:
    """Create missing ZatGo Core roles."""
    for role_name in CORE_ROLES:
        if frappe.db.exists("Role", role_name):
            continue
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
                "is_custom": 1,
            }
        ).insert(ignore_permissions=True)
        logger.info("Created role %s", role_name)
