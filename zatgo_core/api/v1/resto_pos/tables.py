"""Resto POS floor tables — ZG Table DocType. Thin wrappers over resto_pos_service."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import resto_pos_service as svc


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    return svc.list_tables(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return svc.get_table(name)


@frappe.whitelist()
def seat(table_id: str, covers: int | str = 1, client_id: str | None = None) -> dict[str, Any]:
    return svc.seat_table(table_id, covers=covers, client_id=client_id)


@frappe.whitelist()
def set_status(table_id: str, status: str) -> dict[str, Any]:
    return svc.set_table_status(table_id, status)
