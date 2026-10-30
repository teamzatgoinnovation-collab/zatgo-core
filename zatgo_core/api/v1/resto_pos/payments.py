"""Resto POS payments (paid orders with their Sales Invoice / Payment Entry)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import resto_pos_admin_service as svc


@frappe.whitelist()
def list(date: str | None = None, page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    return svc.list_payments(date, page, page_size)
