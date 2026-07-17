"""Documentation doc entries stubs."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.v1._stubs import stub_get, stub_list


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    """List doc entries (stub — empty until DocTypes exist)."""
    return stub_list("documentation", "doc entries", page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    """Get a single doc entrie by name (stub)."""
    return stub_get("documentation", "doc entries", name)
