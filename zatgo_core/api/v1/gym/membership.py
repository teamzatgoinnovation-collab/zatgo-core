"""Gym industry API -- thin wrappers over industries/gym/service.py. Every
method needs login, the Gym industry switched on, a Gym role and the
DocType permissions (industries/gate.py)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.industries.gate import industry_api
from zatgo_core.industries.gym import service

ROLES = ("ZG Gym Manager", "ZG Gym User")


@frappe.whitelist()
@industry_api("gym", ROLES)
def plans() -> dict[str, Any]:
    rows = frappe.get_list(
        "ZG Gym Plan", filters={"is_active": 1}, fields=["name", "plan_name", "duration_days", "price"], limit_page_length=200
    )
    return ok(rows)


@frappe.whitelist(methods=["POST"])
@industry_api("gym", ROLES)
def renew(membership: str) -> dict[str, Any]:
    return ok(service.renew(membership))


@frappe.whitelist(methods=["POST"])
@industry_api("gym", ROLES)
def bill(membership: str) -> dict[str, Any]:
    return ok(service.bill(membership))


@frappe.whitelist(methods=["POST"])
@industry_api("gym", ROLES)
def check_in(membership: str) -> dict[str, Any]:
    return ok(service.check_in(membership))
