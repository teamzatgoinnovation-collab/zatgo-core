"""Go Van health endpoints."""

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
    count = frappe.db.count("ZG Trip") if frappe.db.exists("DocType", "ZG Trip") else 0
    return ok(
        {
            "product": "go_van",
            "title": "Go Van",
            "ready": count > 0,
            "stub": False,
            "count": count,
            "message": (
                "Go Van API reading ERPNext data"
                if count
                else "Go Van API ready — run seed_demo_data"
            ),
            "domain": "trips",
        },
        meta={"stub": False, "count": count},
    )
