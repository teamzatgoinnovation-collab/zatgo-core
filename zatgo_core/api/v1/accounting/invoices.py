"""Accounting — ERPNext Sales Invoice."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_sales_invoice, list_items, list_sales_invoices
from zatgo_core.services.erpnext_writes import create_sales_invoice, submit_sales_invoice


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_sales_invoices(page=page, page_size=page_size)


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_sales_invoice(name)


@frappe.whitelist()
def create(
    customer: str,
    items: str | list | None = None,
    company: str | None = None,
    posting_date: str | None = None,
    due_date: str | None = None,
    remarks: str | None = None,
) -> dict[str, Any]:
    return create_sales_invoice(
        customer=customer,
        items=items,
        company=company,
        posting_date=posting_date,
        due_date=due_date,
        remarks=remarks,
    )


@frappe.whitelist()
def submit(name: str) -> dict[str, Any]:
    return submit_sales_invoice(name)


@frappe.whitelist()
def get_zatca_qr(name: str) -> dict[str, Any]:
    """Return Phase 2 simplified ZATCA QR payload for a Sales Invoice."""
    from zatgo_core.api.response import ok
    from zatgo_core.api.validators import require_login, require_str
    from zatgo_core.services.zatca_qr import generate_and_store_zatca_qr, zatca_fields_from_doc

    require_login()
    require_str(name, "name")
    frappe.has_permission("Sales Invoice", "read", doc=name, throw=True)
    doc = frappe.get_doc("Sales Invoice", name)
    fields = zatca_fields_from_doc(doc)
    qr = fields.get("qr_base64")
    if not qr and int(doc.docstatus or 0) == 1:
        qr = generate_and_store_zatca_qr(doc)
        frappe.db.commit()
        fields["qr_base64"] = qr
    elif not qr:
        # Draft preview — do not persist
        from zatgo_core.services.zatca_qr import build_zatca_tlv_base64

        fields["qr_base64"] = build_zatca_tlv_base64(
            seller_name=str(fields["seller_name"]),
            vat_number=str(fields["vat_number"] or "000000000000000"),
            timestamp=str(fields["timestamp"]),
            invoice_total=fields["invoice_total"],
            vat_amount=fields["vat_amount"],
        )
    return ok(fields, meta={"stub": False, "source": "Sales Invoice"})


@frappe.whitelist()
def list_items_catalog(page: int | str = 1, page_size: int | str = 50) -> dict[str, Any]:
    """Items for invoice line pickers."""
    return list_items(page=page, page_size=page_size)
