"""Go Van collections — Payment Entry Receive with client_id idempotency."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.go_van_service import create_collection


@frappe.whitelist()
def create(
    client_id: str,
    customer: str,
    amount: float | str,
    method: str | None = None,
    sales_invoice: str | None = None,
    posting_date: str | None = None,
) -> dict[str, Any]:
    return create_collection(
        client_id=client_id,
        customer=customer,
        amount=amount,
        method=method,
        sales_invoice=sales_invoice,
        posting_date=posting_date,
    )
