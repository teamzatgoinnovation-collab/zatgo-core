"""Vendor Portal health endpoints."""

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
    count = frappe.db.count("Purchase Order")
    return ok(
        {
            "product": "vendor_portal",
            "title": "Vendor Portal",
            "ready": count > 0,
            "stub": False,
            "count": count,
            "message": (
                "Vendor Portal API reading ERPNext data"
                if count
                else "Vendor Portal API ready — run seed_demo_data"
            ),
            "domain": "purchase_orders",
        },
        meta={"stub": False, "count": count},
    )
