"""Resto POS billing / checkout. Thin wrappers over resto_pos_service."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import resto_pos_service as svc


@frappe.whitelist()
def modes() -> dict[str, Any]:
    return svc.payment_modes()


@frappe.whitelist()
def mark_billing(order_id: str) -> dict[str, Any]:
    return svc.mark_billing(order_id)


@frappe.whitelist()
def pay(order_id: str, method: str, client_id: str) -> dict[str, Any]:
    return svc.pay(order_id, method, client_id)
