"""Jewellery industry API -- thin wrappers over industries/jewellery/service.py."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.industries.gate import industry_api
from zatgo_core.industries.jewellery import service

ROLES = ("ZG Jewellery Manager", "ZG Jewellery User")


@frappe.whitelist()
@industry_api("jewellery", ROLES)
def price(item_code: str, on_date: str | None = None) -> dict[str, Any]:
    return ok(service.price(item_code, on_date))


@frappe.whitelist()
@industry_api("jewellery", ROLES)
def rate(metal: str, purity: str, on_date: str | None = None) -> dict[str, Any]:
    frappe.has_permission("ZG Metal Rate", "read", throw=True)
    return ok({"metal": metal, "purity": purity, "rate_per_gram": service.latest_rate(metal, purity, on_date)})
