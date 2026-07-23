"""Go Van — current user VanSale context."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.van_sale_access import (
    get_profile,
    is_vansale_admin,
    is_vansale_user,
    user_roles,
)


@frappe.whitelist(methods=["GET", "POST"])
def context() -> dict[str, Any]:
    """Bootstrap payload for VanSale Flutter (roles + profile)."""
    require_login()
    user = frappe.session.user
    roles = user_roles(user)
    profile = get_profile(user)

    user_type = profile.get("user_type") if profile else None
    if not user_type:
        user_type = "Admin" if is_vansale_admin(user) else "Field User"

    is_admin = user_type == "Admin"
    is_user = user_type == "Field User"

    full_name = frappe.db.get_value("User", user, "full_name") or user
    return ok(
        {
            "user": user,
            "full_name": full_name,
            "roles": roles,
            "user_type": user_type,
            "vansale_roles": [user_type],
            "is_admin": is_admin,
            "is_user": is_user,
            "has_vansale_access": True,
            "profile": profile,
        },
        meta={"source": "go_van.me"},
    )
