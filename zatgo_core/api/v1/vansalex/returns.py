"""VanSaleX sales returns — credit-note Sales Invoice (is_return=1) with client_id idempotency."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from zatgo_core.services.vansalex_access import require as require_access
from zatgo_core.api.response import paginated
from zatgo_core.api.validators import parse_pagination, require_login
from zatgo_core.services.erpnext_reads import map_sales_invoice_row
from zatgo_core.api.response import ok
from zatgo_core.services.vansalex_service import create_sales_return, get_returnable
from zatgo_core.services.van_sale_access import is_vansale_admin


@frappe.whitelist()
def create(
    client_id: str,
    return_against: str,
    items: str | list | None = None,
    warehouse: str | None = None,
    company: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Credit note against a submitted sale. Stock returns to the caller's
    van warehouse (VanSaleX settings); quantities are capped at what is
    left to return on that invoice."""
    require_login()
    require_access("sales_return")
    return create_sales_return(
        client_id=client_id,
        return_against=return_against,
        items=items,
        warehouse=warehouse,
        company=company,
        reason=reason,
    )


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
    sales_user: str | None = None,
    warehouse: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """List Sales Returns for VanSale (admin: filterable; user: own)."""
    require_login()
    require_access("sales_return", "dashboard", "reports")
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: dict[str, Any] = {"docstatus": ["<", 2], "is_return": 1}
    admin = is_vansale_admin()
    if admin:
        if sales_user:
            filters["owner"] = sales_user
        if warehouse and frappe.db.has_column("Sales Invoice", "set_warehouse"):
            filters["set_warehouse"] = warehouse
    else:
        # Own returns, whichever warehouse (same scoping as orders.list).
        filters["owner"] = frappe.session.user

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
            "is_return",
            "return_against",
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
        mapped["return_against"] = r.get("return_against")
        data.append(mapped)
    payload = paginated(data, page=page_i, page_size=size_i, total=total)
    payload["meta"] = {**payload.get("meta", {}), "source": "Sales Invoice"}
    return payload


@frappe.whitelist()
def returnable(sales_invoice: str) -> dict[str, Any]:
    """Lines of [sales_invoice] with sold / already returned / returnable qty."""
    require_login()
    require_access("sales_return")
    return ok(get_returnable(sales_invoice), meta={"source": "vansalex.returns.returnable"})


@frappe.whitelist()
def pdf(name: str, print_format: str | None = None) -> dict[str, Any]:
    """Return the Sales Return PDF — delegates to vansalex.orders.pdf (generic to any Sales Invoice)."""
    from zatgo_core.api.v1.vansalex.orders import pdf as orders_pdf

    return orders_pdf(name=name, print_format=print_format)
