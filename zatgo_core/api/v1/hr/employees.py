"""HR employees — ERPNext Employee."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_employee, list_employees


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_employees(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_employee(name)
