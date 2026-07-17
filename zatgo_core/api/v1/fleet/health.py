"""Fleet health endpoints."""

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
    count = frappe.db.count("ZG Vehicle") if frappe.db.exists("DocType", "ZG Vehicle") else 0
    return ok(
        {
            "product": "fleet",
            "title": "Fleet",
            "ready": count > 0,
            "stub": False,
            "count": count,
            "message": (
                "Fleet API reading ERPNext data"
                if count
                else "Fleet API ready — run seed_demo_data"
            ),
            "domain": "vehicles",
        },
        meta={"stub": False, "count": count},
    )
