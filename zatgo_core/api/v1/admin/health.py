"""Admin health endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login


@frappe.whitelist()
def ping() -> dict[str, Any]:
    require_login()
    return status()


@frappe.whitelist()
def status() -> dict[str, Any]:
    require_login()
    count = frappe.db.count("Item")
    return ok(
        {
            "product": "admin",
            "title": "Admin",
            "ready": count > 0,
            "stub": False,
            "count": count,
            "message": (
                "Admin API reading ERPNext data"
                if count
                else "Admin API ready — run seed_demo_data"
            ),
            "domain": "overview",
        },
        meta={"stub": False, "count": count},
    )
