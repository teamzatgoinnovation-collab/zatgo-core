"""Go Van orders — Sales Invoice with client_id idempotency."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.go_van_service import create_order


@frappe.whitelist()
def create(
    client_id: str,
    customer: str,
    items: str | list | None = None,
    warehouse: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    return create_order(
        client_id=client_id,
        customer=customer,
        items=items,
        warehouse=warehouse,
        company=company,
    )
