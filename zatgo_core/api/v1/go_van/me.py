"""Go Van — current user VanSale context."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.van_sale_access import (
    ROLE_ADMIN,
    ROLE_USER,
    get_profile,
    is_vansale_admin,
    is_vansale_user,
    user_roles,
)


@frappe.whitelist()
def context() -> dict[str, Any]:
    """Bootstrap payload for VanSale Flutter (roles + profile)."""
    require_login()
    user = frappe.session.user
    roles = user_roles(user)
    vansale_roles = [r for r in roles if r in (ROLE_USER, ROLE_ADMIN)]
    admin = is_vansale_admin(user)
    user_role = is_vansale_user(user)
    profile = get_profile(user)
    full_name = frappe.db.get_value("User", user, "full_name") or user
    return ok(
        {
            "user": user,
            "full_name": full_name,
            "roles": roles,
            "vansale_roles": vansale_roles,
            "is_admin": admin,
            "is_user": user_role,
            "has_vansale_access": admin or user_role or "System Manager" in roles,
            "profile": profile,
        },
        meta={"source": "go_van.me"},
    )
