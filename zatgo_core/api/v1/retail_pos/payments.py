"""Retail POS payments (Payment Entries received against Sales Invoices)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import retail_pos_service as svc


@frappe.whitelist()
def list(date: str | None = None, page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    return svc.list_payments(date, page, page_size)
