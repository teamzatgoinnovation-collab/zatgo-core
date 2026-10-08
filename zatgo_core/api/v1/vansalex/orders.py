"""VanSaleX orders — Sales Invoice with client_id idempotency."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from zatgo_core.services.vansalex_access import require as require_access
from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login
from zatgo_core.services.erpnext_reads import map_sales_invoice_row
from zatgo_core.services.vansalex_service import (
    confirm_order,
    create_order,
    create_sales_order,
    preview_invoice_totals,
)
from zatgo_core.services.van_sale_access import is_vansale_admin


@frappe.whitelist()
def create(
    client_id: str,
    customer: str,
    items: str | list | None = None,
    warehouse: str | None = None,
    company: str | None = None,
    trip_id: str | None = None,
    discount_percentage: float | str | None = None,
    payment_type: str | None = None,
    cash_account: str | None = None,
    payment_details: str | list | None = None,
    bank_account: str | None = None,
    bank_reference_no: str | None = None,
) -> dict[str, Any]:
    """Invoice — creates+submits a Sales Invoice immediately. Warehouse,
    Cash/Bank/Credit and the Cash or Bank account (blank = the default; see
    ``payment_accounts``) are checked against the caller's VanSaleX settings
    (services/vansalex_settings.resolve_sale); a Cash or Bank invoice gets
    its Payment Entry auto-created on submit, a Bank one with
    `bank_reference_no` (else the invoice no.) as reference. `payment_details`
    ([{payment_method, account?, amount, reference_no?, remarks?}]) instead
    records the payment on the invoice itself, split across methods and
    accounts (services/payment_allocation.py)."""
    require_login()
    require_access("sales_invoice")
    return create_order(
        client_id=client_id,
        customer=customer,
        items=items,
        warehouse=warehouse,
        company=company,
        trip_id=trip_id,
        discount_percentage=discount_percentage,
        payment_type=payment_type,
        cash_account=cash_account,
        payment_details=payment_details,
        bank_account=bank_account,
        bank_reference_no=bank_reference_no,
    )


@frappe.whitelist()
def payment_accounts() -> dict[str, Any]:
    """Read-only: the Cash and Bank accounts the caller may sell into,
    default first (``{"cash_account": [{name, is_default}], "bank_account":
    [...]}``) -- all of their company's with "Choose payment account", else
    just the default."""
    from zatgo_core.services.vansalex_settings import selectable_payment_accounts

    require_login()
    require_access("sales_invoice")
    return ok(selectable_payment_accounts(), meta={"source": "Account"})


@frappe.whitelist()
def preview_totals(
    customer: str,
    items: str | list | None = None,
    warehouse: str | None = None,
    company: str | None = None,
    discount_percentage: float | str | None = None,
) -> dict[str, Any]:
    """Read-only: the totals ``create`` would give this sale (ERPNext's own
    calculation, nothing saved) -- ``payable_total`` is what split payments
    must add up to."""
    require_login()
    require_access("sales_invoice")
    return preview_invoice_totals(
        customer=customer,
        items=items,
        warehouse=warehouse,
        company=company,
        discount_percentage=discount_percentage,
    )


@frappe.whitelist()
def create_order_draft(
    client_id: str,
    customer: str,
    items: str | list | None = None,
    company: str | None = None,
    trip_id: str | None = None,
    discount_percentage: float | str | None = None,
) -> dict[str, Any]:
    """Order side of the two-stage flow — creates+submits a real Sales
    Order, no stock/warehouse impact yet. Confirm it via `confirm()`."""
    require_login()
    # sales_order mirrors VanSaleX Settings → Allow Orders; as a module it
    # binds every caller (the service's own check exempts admins).
    require_access("sales_order")
    return create_sales_order(
        client_id=client_id,
        customer=customer,
        items=items,
        company=company,
        trip_id=trip_id,
        discount_percentage=discount_percentage,
    )


@frappe.whitelist()
def confirm(
    client_id: str,
    sales_order: str,
    warehouse: str | None = None,
    company: str | None = None,
    trip_id: str | None = None,
    payment_type: str | None = None,
    cash_account: str | None = None,
    payment_details: str | list | None = None,
    bank_account: str | None = None,
    bank_reference_no: str | None = None,
) -> dict[str, Any]:
    """Confirm a submitted Sales Order into a submitted Sales Invoice
    (Cash/Bank/Credit and its account, warehouse and payment_details as for
    ``create``)."""
    require_login()
    require_access("sales_invoice")
    return confirm_order(
        client_id=client_id,
        sales_order=sales_order,
        warehouse=warehouse,
        company=company,
        trip_id=trip_id,
        payment_type=payment_type,
        cash_account=cash_account,
        payment_details=payment_details,
        bank_account=bank_account,
        bank_reference_no=bank_reference_no,
    )


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
    sales_user: str | None = None,
    warehouse: str | None = None,
    date: str | None = None,
    customer: str | None = None,
) -> dict[str, Any]:
    """List Sales Invoices for VanSale (admin: filterable; user: own)."""
    require_login()
    require_access("sales_invoice", "sales_return", "dashboard", "reports", "documents", "my_performance")
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: dict[str, Any] = {"docstatus": ["<", 2], "is_return": 0}
    admin = is_vansale_admin()
    if admin:
        if sales_user:
            filters["owner"] = sales_user
        if warehouse and frappe.db.has_column("Sales Invoice", "set_warehouse"):
            filters["set_warehouse"] = warehouse
    else:
        # Own invoices, whichever warehouse they were sold from (a driver may
        # be allowed to sell from more than one — see VanSaleX Settings).
        filters["owner"] = frappe.session.user

    if date:
        filters["posting_date"] = str(getdate(date))
    if customer:
        filters["customer"] = customer

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
            "net_total",
            "total_taxes_and_charges",
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
def list_sales_orders(
    page: int | str = 1,
    page_size: int | str = 20,
    sales_user: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """List Sales Orders from the Order -> Confirm -> Invoice flow.

    Same scoping as ``list``: admins may filter by owner, a field user only
    ever sees their own. Each row carries its lines and, once confirmed, the
    Sales Invoice it became — so a client with no local store can reprint the
    order receipt or offer Confirm straight from this list.
    """
    require_login()
    require_access("sales_order", "sales_invoice", "dashboard", "documents", "my_performance")
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: dict[str, Any] = {"docstatus": ["<", 2]}
    if is_vansale_admin():
        if sales_user:
            filters["owner"] = sales_user
    else:
        filters["owner"] = frappe.session.user
    if date:
        filters["transaction_date"] = str(getdate(date))

    total = frappe.db.count("Sales Order", filters)
    rows = frappe.get_all(
        "Sales Order",
        filters=filters,
        fields=[
            "name",
            "customer",
            "customer_name",
            "transaction_date",
            "status",
            "docstatus",
            "per_billed",
            "net_total",
            "total_taxes_and_charges",
            "grand_total",
            "rounded_total",
            "additional_discount_percentage",
            "zatgo_client_id",
            "creation",
        ],
        order_by="creation desc",
        start=start,
        page_length=size_i,
    )
    names = [r.name for r in rows]
    items_by_order: dict[str, list[dict[str, Any]]] = {n: [] for n in names}
    invoice_by_order: dict[str, str] = {}
    if names:
        for it in frappe.get_all(
            "Sales Order Item",
            filters={"parent": ["in", names]},
            fields=["parent", "item_code", "item_name", "qty", "rate"],
            order_by="idx asc",
        ):
            items_by_order[it.parent].append(
                {
                    "item_code": it.item_code,
                    "item_name": it.item_name,
                    "qty": float(it.qty or 0),
                    "rate": float(it.rate or 0),
                }
            )
        for si in frappe.get_all(
            "Sales Invoice Item",
            filters={"sales_order": ["in", names], "docstatus": 1},
            fields=["sales_order", "parent"],
        ):
            invoice_by_order.setdefault(si.sales_order, si.parent)

    data = [
        {
            "id": r.name,
            "name": r.name,
            "client_id": r.zatgo_client_id,
            "customer": r.customer_name or r.customer,
            "customer_id": r.customer,
            "date": str(r.transaction_date or ""),
            "created_at": str(r.creation or ""),
            "status": r.status,
            "docstatus": int(r.docstatus or 0),
            "per_billed": float(r.per_billed or 0),
            "net_total": float(r.net_total or 0),
            "total_taxes_and_charges": float(r.total_taxes_and_charges or 0),
            "grand_total": float(r.grand_total or 0),
            "rounded_total": float(r.rounded_total or r.grand_total or 0),
            "discount_percentage": float(r.additional_discount_percentage or 0),
            "sales_invoice": invoice_by_order.get(r.name),
            "items": items_by_order.get(r.name, []),
        }
        for r in rows
    ]
    payload = paginated(data, page=page_i, page_size=size_i, total=total)
    payload["meta"] = {**payload.get("meta", {}), "source": "Sales Order"}
    return payload


@frappe.whitelist()
def pdf(name: str, print_format: str | None = None) -> dict[str, Any]:
    """Sales Invoice PDF (base64). Without [print_format]: the site's
    default Sales Invoice print format set in ERPNext."""
    import base64

    from zatgo_core.api.response import ok
    from zatgo_core.api.validators import require_str
    from zatgo_core.services.vansalex_settings import default_print_format

    require_login()
    invoice = require_str(name, "name")
    if not frappe.db.exists("Sales Invoice", invoice):
        frappe.throw(f"Sales Invoice not found: {invoice}", frappe.DoesNotExistError)
    frappe.has_permission("Sales Invoice", "read", doc=invoice, throw=True)

    docstatus = int(frappe.db.get_value("Sales Invoice", invoice, "docstatus") or 0)
    if docstatus != 1:
        frappe.throw(
            f"Sales Invoice {invoice} is not submitted yet (docstatus={docstatus}).",
            frappe.ValidationError,
        )

    fmt = (print_format or "").strip() or default_print_format()
    if not frappe.db.exists("Print Format", fmt):
        fmt = default_print_format()
    # Printing is read-only, but which papers a client prints on is a
    # VanSaleX feature: the thermal format is "80mm", anything else is A4.
    from zatgo_core.setup.ensure_print_formats import PRINT_FORMAT_80MM_NAME

    require_access("sales_invoice", "sales_return", "documents")
    require_access(
        "sales_invoice.print_80mm" if fmt == PRINT_FORMAT_80MM_NAME else "sales_invoice.print_a4"
    )

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
        meta={"source": "vansalex.orders.pdf"},
    )
