"""VanSaleX purchases — Purchase Invoice / Purchase Order into the van
warehouse (services/vansalex_purchase_service.py). Each endpoint needs its
module switched on for the caller (VanSaleX Settings → Modules & Features)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.vansalex_access import require as require_access
from zatgo_core.services import vansalex_purchase_service as svc

_KIND_MODULE = {"invoice": "purchase_invoice", "order": "purchase_order"}


def _module(kind: str) -> str:
    module = _KIND_MODULE.get((kind or "").strip().lower())
    if not module:
        frappe.throw("kind must be 'invoice' or 'order'.")
    return module


@frappe.whitelist()
def suppliers(search: str | None = None, limit: int | str = 50) -> dict[str, Any]:
    """Enabled suppliers for the picker, filtered by name."""
    require_login()
    require_access("purchase_invoice", "purchase_order")
    svc.require_purchase_user()
    return ok(svc.list_suppliers(search, limit), meta={"source": "Supplier"})


@frappe.whitelist()
def create_invoice(
    client_id: str,
    supplier: str,
    items: str | list | None = None,
    warehouse: str | None = None,
    payment_type: str | None = None,
    cash_account: str | None = None,
    bank_account: str | None = None,
    bank_reference_no: str | None = None,
    supplier_invoice_no: str | None = None,
) -> dict[str, Any]:
    """Purchase Invoice — created and submitted at once; the goods are
    received into the van warehouse. Cash / Bank / Credit and its account
    follow the VanSaleX settings as for a sale (a Cash or Bank bill gets its
    Payment Entry on submit). `items`: [{item_code, qty, rate}] — rate blank
    = the item's last purchase rate."""
    require_login()
    require_access("purchase_invoice")
    return svc.create_invoice(
        client_id=client_id,
        supplier=supplier,
        items=items,
        warehouse=warehouse,
        payment_type=payment_type,
        cash_account=cash_account,
        bank_account=bank_account,
        bank_reference_no=bank_reference_no,
        supplier_invoice_no=supplier_invoice_no,
    )


@frappe.whitelist()
def create_order(client_id: str, supplier: str, items: str | list | None = None) -> dict[str, Any]:
    """Purchase Order — submitted, nothing received yet (see ``confirm``)."""
    require_login()
    require_access("purchase_order")
    return svc.create_order(client_id=client_id, supplier=supplier, items=items)


@frappe.whitelist()
def confirm(
    client_id: str,
    purchase_order: str,
    warehouse: str | None = None,
    payment_type: str | None = None,
    cash_account: str | None = None,
    bank_account: str | None = None,
    bank_reference_no: str | None = None,
    supplier_invoice_no: str | None = None,
) -> dict[str, Any]:
    """Receive a Purchase Order: its Purchase Invoice, as for
    ``create_invoice``. `client_id` keys the resulting invoice."""
    require_login()
    require_access("purchase_invoice")
    return svc.confirm_order(
        client_id=client_id,
        purchase_order=purchase_order,
        warehouse=warehouse,
        payment_type=payment_type,
        cash_account=cash_account,
        bank_account=bank_account,
        bank_reference_no=bank_reference_no,
        supplier_invoice_no=supplier_invoice_no,
    )


@frappe.whitelist()
def list(kind: str = "invoice", page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    """The caller's purchase invoices (kind=invoice) or orders (kind=order)."""
    require_login()
    require_access(_module(kind))
    return svc.list_purchases(kind, page, page_size)


@frappe.whitelist()
def pdf(kind: str, name: str, print_format: str | None = None) -> dict[str, Any]:
    """PDF (base64) of one of the caller's submitted purchase documents."""
    require_login()
    require_access(_module(kind))
    return svc.purchase_pdf(kind, name, print_format)
