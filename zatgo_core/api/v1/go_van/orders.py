"""Go Van orders — Sales Invoice with client_id idempotency."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from zatgo_core.api.response import paginated
from zatgo_core.api.validators import parse_pagination, require_login
from zatgo_core.services.erpnext_reads import map_sales_invoice_row
from zatgo_core.services.go_van_service import create_order
from zatgo_core.services.van_sale_access import get_profile, is_vansale_admin


@frappe.whitelist()
def create(
    client_id: str,
    customer: str,
    items: str | list | None = None,
    warehouse: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    wh = (warehouse or "").strip()
    if not wh:
        profile = get_profile()
        if profile and profile.get("warehouse"):
            wh = profile["warehouse"]
    return create_order(
        client_id=client_id,
        customer=customer,
        items=items,
        warehouse=wh or None,
        company=company,
    )


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
    sales_user: str | None = None,
    warehouse: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """List Sales Invoices for VanSale (admin: filterable; user: own)."""
    require_login()
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: dict[str, Any] = {"docstatus": ["<", 2]}
    admin = is_vansale_admin()
    if admin:
        if sales_user:
            filters["owner"] = sales_user
        if warehouse and frappe.db.has_column("Sales Invoice", "set_warehouse"):
            filters["set_warehouse"] = warehouse
    else:
        filters["owner"] = frappe.session.user
        profile = get_profile()
        if (
            profile
            and profile.get("warehouse")
            and frappe.db.has_column("Sales Invoice", "set_warehouse")
        ):
            filters["set_warehouse"] = profile["warehouse"]

    if date:
        filters["posting_date"] = str(getdate(date))

    total = frappe.db.count("Sales Invoice", filters)
    rows = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=[
            "name",
            "customer",
            "customer_name",
            "grand_total",
            "outstanding_amount",
            "posting_date",
            "status",
            "docstatus",
            "owner",
            "set_warehouse",
            "modified",
        ],
        order_by="posting_date desc, modified desc",
        start=start,
        page_length=size_i,
    )
    data = []
    for r in rows:
        mapped = map_sales_invoice_row(r)
        mapped["owner"] = r.get("owner")
        mapped["warehouse"] = r.get("set_warehouse")
        mapped["posting_date"] = str(r.get("posting_date") or "")
        data.append(mapped)
    payload = paginated(data, page=page_i, page_size=size_i, total=total)
    payload["meta"] = {**payload.get("meta", {}), "source": "Sales Invoice"}
    return payload


@frappe.whitelist()
def pdf(name: str, print_format: str | None = None) -> dict[str, Any]:
    """Return Sales Invoice PDF (base64) using VanSale Tax Invoice format."""
    import base64

    from zatgo_core.api.response import ok
    from zatgo_core.api.validators import require_str
    from zatgo_core.setup.ensure_print_formats import PRINT_FORMAT_NAME

    require_login()
    invoice = require_str(name, "name")
    if not frappe.db.exists("Sales Invoice", invoice):
        frappe.throw(f"Sales Invoice not found: {invoice}", frappe.DoesNotExistError)
    frappe.has_permission("Sales Invoice", "read", doc=invoice, throw=True)

    fmt = (print_format or "").strip() or PRINT_FORMAT_NAME
    if not frappe.db.exists("Print Format", fmt):
        fmt = "Standard"

    pdf_bytes = frappe.get_print(
        "Sales Invoice",
        invoice,
        print_format=fmt,
        as_pdf=True,
    )
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("utf-8")

    return ok(
        {
            "name": invoice,
            "print_format": fmt,
            "content_type": "application/pdf",
            "filename": f"{invoice}.pdf",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        },
        meta={"source": "go_van.orders.pdf"},
    )
