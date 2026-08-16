"""Warehouse — ERPNext Item Group."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import list_item_groups
from zatgo_core.services.erpnext_writes import create_item_group


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    return list_item_groups(page=page, page_size=page_size)


@frappe.whitelist()
def create(
    item_group_name: str,
    parent_item_group: str | None = None,
    is_group: int | str | None = None,
) -> dict[str, Any]:
    return create_item_group(
        item_group_name=item_group_name,
        parent_item_group=parent_item_group,
        is_group=is_group,
    )
