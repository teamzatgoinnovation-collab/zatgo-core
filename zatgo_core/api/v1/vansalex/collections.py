"""VanSaleX collections — Payment Entry Receive with client_id idempotency."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from zatgo_core.services.vansalex_access import require as require_access
from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login
from zatgo_core.services.erpnext_reads import map_payment_entry_row
from zatgo_core.services.vansalex_service import create_collection
from zatgo_core.services.van_sale_access import is_vansale_admin


@frappe.whitelist()
def modes(company: str | None = None) -> dict[str, Any]:
    """Mode of Payment options for the New Collection form — the app must
    only offer values that exist here, since create() sets mode_of_payment
    as a Link field and an unknown value fails with LinkValidationError.
    `methods` adds each mode's allowed accounts (default first) for the
    caller's company, for building `payment_details`."""
    require_access("collections", "sales_invoice")
    from zatgo_core.services.payment_allocation import allowed_accounts
    from zatgo_core.services.vansalex_settings import resolve

    require_login()
    rows = frappe.get_all(
        "Mode of Payment",
        filters={"enabled": 1},
        fields=["name", "type"],
        order_by="name asc",
    )
    company = (company or "").strip() or resolve().get("company")
    methods = [
        {"name": r.name, "type": r.type, "accounts": allowed_accounts(r.name, company) if company else []}
        for r in rows
    ]
    return ok({"modes": [r.name for r in rows], "company": company, "methods": methods})


@frappe.whitelist()
def create(
    client_id: str,
    customer: str,
    amount: float | str | None = None,
    method: str | None = None,
    sales_invoice: str | None = None,
    posting_date: str | None = None,
    reference: str | None = None,
    notes: str | None = None,
    payment_details: str | list | None = None,
) -> dict[str, Any]:
    """Receive a customer payment. Either `amount` (+ optional `method`) or
    `payment_details` ([{payment_method, account?, amount, reference_no?,
    remarks?}]) to split it across methods/accounts; with both, `amount`
    must equal the rows' total."""
    require_access("collections")
    return create_collection(
        client_id=client_id,
        customer=customer,
        amount=amount,
        method=method,
        sales_invoice=sales_invoice,
        posting_date=posting_date,
        reference=reference,
        notes=notes,
        payment_details=payment_details,
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
    require_access("collections", "dashboard", "reports", "my_performance")
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
