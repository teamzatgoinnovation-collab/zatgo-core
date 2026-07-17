"""ZatGo POS health endpoints."""

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
    items = frappe.db.count("Item", {"disabled": 0})
    kds = (
        frappe.db.count("ZG KDS Ticket", {"status": ("!=", "Served")})
        if frappe.db.exists("DocType", "ZG KDS Ticket")
        else 0
    )
    count = items + kds
    return ok(
        {
            "product": "resto_pos",
            "title": "ZatGo POS",
            "ready": count > 0,
            "stub": False,
            "count": count,
            "items": items,
            "kds_open": kds,
            "message": (
                "ZatGo POS API reading ERPNext catalog + KDS"
                if count
                else "ZatGo POS API ready — run seed_demo_data"
            ),
            "domain": "catalog",
        },
        meta={"stub": False, "count": count, "items": items, "kds_open": kds},
    )
