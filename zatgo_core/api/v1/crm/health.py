"""CRM health endpoints."""

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
    count = frappe.db.count("Lead")
    return ok(
        {
            "product": "crm",
            "title": "CRM",
            "ready": count > 0,
            "stub": False,
            "count": count,
            "message": (
                "CRM API reading ERPNext data"
                if count
                else "CRM API ready — run seed_demo_data"
            ),
            "domain": "leads",
        },
        meta={"stub": False, "count": count},
    )
