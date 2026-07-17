"""Delivery health endpoints."""

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
    stop_count = (
        frappe.db.count("ZG Delivery Stop")
        if frappe.db.exists("DocType", "ZG Delivery Stop")
        else 0
    )
    boy_count = (
        frappe.db.count("ZG Delivery Boy")
        if frappe.db.exists("DocType", "ZG Delivery Boy")
        else 0
    )
    return ok(
        {
            "product": "delivery",
            "title": "Delivery",
            "ready": stop_count > 0,
            "stub": False,
            "count": stop_count,
            "delivery_boys": boy_count,
            "message": (
                "Delivery API reading ERPNext data"
                if stop_count
                else "Delivery API ready — run seed_demo_data"
            ),
            "domain": "stops",
        },
        meta={"stub": False, "count": stop_count, "delivery_boys": boy_count},
    )
