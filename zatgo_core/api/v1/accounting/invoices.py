"""Accounting — ERPNext Sales Invoice."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_sales_invoice, list_sales_invoices


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_sales_invoices(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_sales_invoice(name)
