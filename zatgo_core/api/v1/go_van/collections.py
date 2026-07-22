"""Go Van collections — Payment Entry Receive with client_id idempotency."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from zatgo_core.api.response import paginated
from zatgo_core.api.validators import parse_pagination, require_login
from zatgo_core.services.erpnext_reads import map_payment_entry_row
from zatgo_core.services.go_van_service import create_collection
from zatgo_core.services.van_sale_access import is_vansale_admin


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


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
    sales_user: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """List Payment Entries (Receive) for VanSale."""
    require_login()
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: dict[str, Any] = {
        "docstatus": ["<", 2],
        "payment_type": "Receive",
    }
    admin = is_vansale_admin()
    if admin:
        if sales_user:
            filters["owner"] = sales_user
    else:
        filters["owner"] = frappe.session.user

    if date:
        filters["posting_date"] = str(getdate(date))

    total = frappe.db.count("Payment Entry", filters)
    rows = frappe.get_all(
        "Payment Entry",
        filters=filters,
        fields=[
            "name",
            "party",
            "party_name",
            "paid_amount",
            "posting_date",
            "mode_of_payment",
            "status",
            "docstatus",
            "owner",
            "modified",
        ],
        order_by="posting_date desc, modified desc",
        start=start,
        page_length=size_i,
    )
    data = []
    for r in rows:
        mapped = map_payment_entry_row(r)
        mapped["owner"] = r.get("owner")
        mapped["posting_date"] = str(r.get("posting_date") or "")
        data.append(mapped)
    payload = paginated(data, page=page_i, page_size=size_i, total=total)
    payload["meta"] = {**payload.get("meta", {}), "source": "Payment Entry"}
    return payload
