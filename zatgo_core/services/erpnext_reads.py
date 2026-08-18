"""List/get helpers over ERPNext core DocTypes for zatgo_core product endpoints."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, getdate, nowdate

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_doc_permission, require_login


def _list_doctype(
    doctype: str,
    *,
    fields: list[str],
    page: int | str = 1,
    page_size: int | str = 20,
    filters: dict[str, Any] | None = None,
    order_by: str = "modified desc",
    map_row: Any = None,
) -> dict[str, Any]:
    require_login()
    require_doc_permission(doctype, "read")
    page_i, size_i, start = parse_pagination(page, page_size)
    filt = filters or {}
    total = frappe.db.count(doctype, filt)
    rows = frappe.get_all(
        doctype,
        filters=filt,
        fields=fields,
        order_by=order_by,
        start=start,
        page_length=size_i,
    )
    data = [map_row(r) if map_row else dict(r) for r in rows]
    payload = paginated(data, page=page_i, page_size=size_i, total=total, sort=order_by)
    payload["meta"] = {
        **payload.get("meta", {}),
        "stub": False,
        "source": doctype,
    }
    return payload


def _get_doctype(doctype: str, name: str, *, map_doc: Any = None) -> dict[str, Any]:
    require_login()
    require_doc_permission(doctype, "read", doc=name)
    if not frappe.db.exists(doctype, name):
        frappe.throw(f"{doctype} {name} not found", frappe.DoesNotExistError)
    doc = frappe.get_doc(doctype, name)
    data = map_doc(doc) if map_doc else doc.as_dict()
    return ok(data, meta={"stub": False, "source": doctype})


def map_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("name"),
        "name": row.get("item_name") or row.get("name"),
        "item_code": row.get("name"),
        "item_name": row.get("item_name"),
        "item_group": row.get("item_group"),
        "category": row.get("item_group"),
        "brand": row.get("brand") or "",
        "image": row.get("image") or "",
        "price": float(row.get("standard_rate") or 0),
        "rate": float(row.get("standard_rate") or 0),
        "standard_rate": float(row.get("standard_rate") or 0),
        "station": "counter",
        "available": 1 if row.get("disabled") in (0, "0", None, False) else 0,
        "sku": row.get("sku") or row.get("name"),
        "barcode": row.get("barcode") or "",
        "uom": row.get("stock_uom"),
        "stock_uom": row.get("stock_uom"),
        "sales_uom": row.get("sales_uom") or "",
        "description": row.get("description") or "",
        "has_batch_no": int(row.get("has_batch_no") or 0),
        "has_serial_no": int(row.get("has_serial_no") or 0),
        "is_sales_item": int(row.get("is_sales_item") if row.get("is_sales_item") is not None else 1),
        "is_purchase_item": int(row.get("is_purchase_item") if row.get("is_purchase_item") is not None else 1),
        "weight_per_unit": float(row.get("weight_per_unit") or 0),
        "weight_uom": row.get("weight_uom") or "",
        "default_warehouse": row.get("default_warehouse") or "",
        "reorder_level": float(row.get("reorder_level") or 0),
        "reorder_qty": float(row.get("reorder_qty") or 0),
        "tax_template": row.get("tax_template") or "",
        "disabled": row.get("disabled"),
        "modified": row.get("modified"),
        "verticals": [],
    }


def list_items(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    fields = [
        "name",
        "item_name",
        "item_group",
        "standard_rate",
        "stock_uom",
        "disabled",
        "brand",
        "image",
        "modified",
    ]
    if frappe.db.has_column("Item", "sku"):
        fields.append("sku")
    return _list_doctype(
        "Item",
        fields=fields,
        page=page,
        page_size=page_size,
        filters={"disabled": 0},
        map_row=map_item_row,
    )


def get_item(name: str) -> dict[str, Any]:
    def map_doc(doc: Any) -> dict[str, Any]:
        barcode = ""
        if getattr(doc, "barcodes", None):
            barcode = doc.barcodes[0].barcode if doc.barcodes else ""
        default_warehouse = doc.item_defaults[0].default_warehouse if getattr(doc, "item_defaults", None) else None
        reorder_row = doc.reorder_levels[0] if getattr(doc, "reorder_levels", None) else None
        tax_row = doc.taxes[0] if getattr(doc, "taxes", None) else None
        return map_item_row(
            {
                "name": doc.name,
                "item_name": doc.item_name,
                "item_group": doc.item_group,
                "standard_rate": doc.standard_rate,
                "stock_uom": doc.stock_uom,
                "disabled": doc.disabled,
                "barcode": barcode,
                "brand": doc.brand,
                "description": doc.description,
                "sales_uom": getattr(doc, "sales_uom", None),
                "has_batch_no": doc.has_batch_no,
                "has_serial_no": doc.has_serial_no,
                "is_sales_item": doc.is_sales_item,
                "is_purchase_item": doc.is_purchase_item,
                "weight_per_unit": doc.weight_per_unit,
                "weight_uom": doc.weight_uom,
                "default_warehouse": default_warehouse,
                "reorder_level": reorder_row.warehouse_reorder_level if reorder_row else 0,
                "reorder_qty": reorder_row.warehouse_reorder_qty if reorder_row else 0,
                "tax_template": tax_row.item_tax_template if tax_row else None,
            }
        )

    return _get_doctype("Item", name, map_doc=map_doc)


def enrich_customer_doc(d: Any) -> dict[str, Any]:
    return {
        "id": d.name,
        "name": d.customer_name,
        "customer_name": d.customer_name,
        "customer_type": d.customer_type,
        "territory": d.territory,
        "email": getattr(d, "email_id", None),
        "phone": getattr(d, "mobile_no", None),
        "customer_group": getattr(d, "customer_group", None),
        "disabled": int(getattr(d, "disabled", 0) or 0),
    }


def list_customers(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    fields = [
        "name",
        "customer_name",
        "customer_type",
        "territory",
        "customer_group",
        "disabled",
        "mobile_no",
        "email_id",
        "tax_id",
        "modified",
    ]
    # Optional custom / extended columns when present on Customer
    for col in (
        "zatgo_customer_name_ar",
        "zatgo_cr_number",
        "zatgo_customer_code",
        "zatgo_barcode",
        "customer_primary_contact",
    ):
        if frappe.db.has_column("Customer", col):
            fields.append(col)

    def _map(r: Any) -> dict[str, Any]:
        row = dict(r) if not isinstance(r, dict) else r
        return {
            "id": row.get("name"),
            "name": row.get("customer_name") or row.get("name"),
            "customer_name": row.get("customer_name"),
            "customer_name_ar": row.get("zatgo_customer_name_ar"),
            "customer_type": row.get("customer_type"),
            "territory": row.get("territory"),
            "customer_group": row.get("customer_group"),
            "mobile_no": row.get("mobile_no"),
            "phone": row.get("mobile_no"),
            "email": row.get("email_id"),
            "email_id": row.get("email_id"),
            "tax_id": row.get("tax_id"),
            "cr_number": row.get("zatgo_cr_number"),
            "customer_code": row.get("zatgo_customer_code") or row.get("name"),
            "barcode": row.get("zatgo_barcode") or "",
            "modified": row.get("modified"),
        }

    return _list_doctype(
        "Customer",
        fields=fields,
        page=page,
        page_size=page_size,
        filters={"disabled": 0},
        map_row=_map,
    )


def get_customer(name: str) -> dict[str, Any]:
    return _get_doctype("Customer", name, map_doc=enrich_customer_doc)


def list_leads(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Lead",
        fields=["name", "lead_name", "company_name", "status", "email_id", "mobile_no"],
        page=page,
        page_size=page_size,
        map_row=lambda r: {
            "id": r.name,
            "name": r.lead_name or r.name,
            "title": r.lead_name or r.company_name or r.name,
            "company": r.company_name,
            "status": r.status,
            "email": r.email_id,
            "phone": r.mobile_no,
        },
    )


def get_lead(name: str) -> dict[str, Any]:
    return _get_doctype(
        "Lead",
        name,
        map_doc=lambda d: {
            "id": d.name,
            "name": d.lead_name,
            "title": d.lead_name or d.company_name,
            "company": d.company_name,
            "status": d.status,
            "email": d.email_id,
            "phone": d.mobile_no,
        },
    )


def list_employees(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Employee",
        fields=["name", "employee_name", "department", "designation", "status", "company"],
        page=page,
        page_size=page_size,
        filters={"status": "Active"},
        map_row=lambda r: {
            "id": r.name,
            "name": r.employee_name or r.name,
            "department": r.department,
            "designation": r.designation,
            "status": r.status,
            "company": r.company,
        },
    )


def get_employee(name: str) -> dict[str, Any]:
    return _get_doctype(
        "Employee",
        name,
        map_doc=lambda d: {
            "id": d.name,
            "name": d.employee_name,
            "department": d.department,
            "designation": d.designation,
            "status": d.status,
            "company": d.company,
        },
    )


def list_sales_orders(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Sales Order",
        fields=["name", "customer", "customer_name", "status", "grand_total", "transaction_date"],
        page=page,
        page_size=page_size,
        map_row=lambda r: {
            "id": r.name,
            "name": r.name,
            "customer": r.customer_name or r.customer,
            "status": r.status,
            "amount": float(r.grand_total or 0),
            "date": str(r.transaction_date) if r.transaction_date else None,
        },
    )


def get_sales_order(name: str) -> dict[str, Any]:
    return _get_doctype(
        "Sales Order",
        name,
        map_doc=lambda d: {
            "id": d.name,
            "name": d.name,
            "customer": d.customer_name or d.customer,
            "status": d.status,
            "amount": float(d.grand_total or 0),
            "date": str(d.transaction_date) if d.transaction_date else None,
        },
    )


def list_purchase_orders(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Purchase Order",
        fields=["name", "supplier", "supplier_name", "status", "grand_total", "transaction_date"],
        page=page,
        page_size=page_size,
        map_row=lambda r: {
            "id": r.name,
            "name": r.name,
            "supplier": r.supplier_name or r.supplier,
            "status": r.status,
            "amount": float(r.grand_total or 0),
            "date": str(r.transaction_date) if r.transaction_date else None,
        },
    )


def get_purchase_order(name: str) -> dict[str, Any]:
    return _get_doctype(
        "Purchase Order",
        name,
        map_doc=lambda d: {
            "id": d.name,
            "name": d.name,
            "supplier": d.supplier_name or d.supplier,
            "status": d.status,
            "amount": float(d.grand_total or 0),
            "date": str(d.transaction_date) if d.transaction_date else None,
        },
    )


def list_warehouses(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Warehouse",
        fields=["name", "warehouse_name", "company", "is_group", "disabled"],
        page=page,
        page_size=page_size,
        filters={"disabled": 0, "is_group": 0},
        map_row=lambda r: {
            "id": r.name,
            "name": r.warehouse_name or r.name,
            "company": r.company,
        },
    )


def list_item_groups(page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    return _list_doctype(
        "Item Group",
        fields=["name", "item_group_name", "parent_item_group", "is_group"],
        page=page,
        page_size=page_size,
        order_by="item_group_name asc",
        map_row=lambda r: {
            "id": r.name,
            "name": r.item_group_name or r.name,
            "parent_item_group": r.parent_item_group,
            "is_group": int(r.is_group or 0),
        },
    )


def list_stock(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    """Stock balances from Bin (item × warehouse)."""
    require_login()
    require_doc_permission("Bin", "read")
    page_i, size_i, start = parse_pagination(page, page_size)
    total = frappe.db.count("Bin", {"actual_qty": [">", 0]})
    rows = frappe.get_all(
        "Bin",
        filters={"actual_qty": [">", 0]},
        fields=["item_code", "warehouse", "actual_qty", "stock_uom", "valuation_rate"],
        order_by="modified desc",
        start=start,
        page_length=size_i,
    )
    data = [
        {
            "id": f"{r.item_code}@{r.warehouse}",
            "name": r.item_code,
            "item_code": r.item_code,
            "warehouse": r.warehouse,
            "qty": float(r.actual_qty or 0),
            "uom": r.stock_uom,
            "rate": float(r.valuation_rate or 0),
        }
        for r in rows
    ]
    payload = paginated(data, page=page_i, page_size=size_i, total=total, sort="modified desc")
    payload["meta"] = {**payload.get("meta", {}), "stub": False, "source": "Bin"}
    return payload


def list_zg(
    doctype: str,
    *,
    fields: list[str],
    page: int | str = 1,
    page_size: int | str = 20,
    filters: dict[str, Any] | None = None,
    order_by: str = "modified desc",
    map_row: Any = None,
) -> dict[str, Any]:
    """List a zatgo_core custom DocType (created by seed / migrate)."""
    if not frappe.db.exists("DocType", doctype):
        require_login()
        page_i, size_i, _ = parse_pagination(page, page_size)
        payload = paginated([], page=page_i, page_size=size_i, total=0)
        payload["meta"] = {
            **payload.get("meta", {}),
            "stub": True,
            "source": doctype,
            "message": f"{doctype} not installed — run seed_demo_data",
        }
        return payload
    return _list_doctype(
        doctype,
        fields=fields,
        page=page,
        page_size=page_size,
        filters=filters,
        order_by=order_by,
        map_row=map_row or (lambda r: dict(r)),
    )


def get_zg(doctype: str, name: str, *, map_doc: Any = None) -> dict[str, Any]:
    if not frappe.db.exists("DocType", doctype):
        require_login()
        return ok(
            None,
            meta={
                "stub": True,
                "source": doctype,
                "message": f"{doctype} not installed — run seed_demo_data",
            },
        )
    return _get_doctype(doctype, name, map_doc=map_doc)


# --- Accounting (AR/AP) -------------------------------------------------


def _invoice_items(doc: Any) -> list[dict[str, Any]]:
    return [
        {
            "item_code": row.item_code,
            "item_name": row.item_name,
            "qty": float(row.qty or 0),
            "rate": float(row.rate or 0),
            "amount": float(row.amount or 0),
            "uom": row.uom,
        }
        for row in (doc.items or [])
    ]


def map_sales_invoice_row(r: Any) -> dict[str, Any]:
    return {
        "id": r.name,
        "name": r.name,
        "customer": r.customer_name or r.customer,
        "customer_id": r.customer,
        "status": r.status,
        "amount": float(r.grand_total or 0),
        "outstanding": float(getattr(r, "outstanding_amount", None) or 0),
        "date": str(r.posting_date) if r.posting_date else None,
        "due_date": str(r.due_date) if getattr(r, "due_date", None) else None,
        "currency": getattr(r, "currency", None),
        "is_return": bool(int(getattr(r, "is_return", 0) or 0)),
        "return_against": getattr(r, "return_against", None),
        "net_total": float(getattr(r, "net_total", None) or 0),
        "total_taxes_and_charges": float(getattr(r, "total_taxes_and_charges", None) or 0),
    }


def map_sales_invoice_doc(d: Any) -> dict[str, Any]:
    row = map_sales_invoice_row(d)
    row["items"] = _invoice_items(d)
    row["company"] = d.company
    row["remarks"] = d.remarks
    row["docstatus"] = int(d.docstatus or 0)
    row["total_taxes_and_charges"] = float(getattr(d, "total_taxes_and_charges", None) or 0)
    row["zatca_qr_base64"] = getattr(d, "zatca_qr_base64", None)
    return row


def list_sales_invoices(
    page: int | str = 1, page_size: int | str = 20, customer: str | None = None
) -> dict[str, Any]:
    filters: dict[str, Any] = {"customer": customer} if customer else None
    return _list_doctype(
        "Sales Invoice",
        fields=[
            "name",
            "customer",
            "customer_name",
            "status",
            "grand_total",
            "outstanding_amount",
            "posting_date",
            "due_date",
            "currency",
            "is_return",
            "return_against",
        ],
        page=page,
        page_size=page_size,
        filters=filters,
        order_by="posting_date desc",
        map_row=map_sales_invoice_row,
    )


def get_sales_invoice(name: str) -> dict[str, Any]:
    return _get_doctype("Sales Invoice", name, map_doc=map_sales_invoice_doc)


def map_quotation_row(r: Any) -> dict[str, Any]:
    return {
        "id": r.name,
        "name": r.name,
        "customer": r.customer_name or r.party_name,
        "customer_id": r.party_name,
        "status": r.status,
        "amount": float(r.grand_total or 0),
        "date": str(r.transaction_date) if r.transaction_date else None,
        "valid_till": str(r.valid_till) if getattr(r, "valid_till", None) else None,
        "currency": getattr(r, "currency", None),
        "docstatus": int(r.docstatus or 0),
    }


def map_quotation_doc(d: Any) -> dict[str, Any]:
    row = map_quotation_row(d)
    row["items"] = [
        {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "description": item.description,
            "qty": float(item.qty or 0),
            "rate": float(item.rate or 0),
            "amount": float(item.amount or 0),
            "billing_type": getattr(item, "zatgo_billing_type", None),
        }
        for item in (d.items or [])
    ]
    row["company"] = d.company
    row["terms"] = d.terms
    return row


def list_quotations(page: int | str = 1, page_size: int | str = 20, customer: str | None = None) -> dict[str, Any]:
    filters: dict[str, Any] = {"party_name": customer} if customer else None
    return _list_doctype(
        "Quotation",
        fields=[
            "name",
            "party_name",
            "customer_name",
            "status",
            "grand_total",
            "transaction_date",
            "valid_till",
            "currency",
            "docstatus",
        ],
        page=page,
        page_size=page_size,
        filters=filters,
        map_row=map_quotation_row,
    )


def get_quotation(name: str) -> dict[str, Any]:
    return _get_doctype("Quotation", name, map_doc=map_quotation_doc)


def list_suppliers(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Supplier",
        fields=["name", "supplier_name", "supplier_type", "supplier_group", "disabled", "country"],
        page=page,
        page_size=page_size,
        filters={"disabled": 0},
        map_row=lambda r: {
            "id": r.name,
            "name": r.supplier_name or r.name,
            "supplier_name": r.supplier_name,
            "supplier_type": r.supplier_type,
            "supplier_group": r.supplier_group,
            "country": r.country,
        },
    )


def get_supplier(name: str) -> dict[str, Any]:
    return _get_doctype(
        "Supplier",
        name,
        map_doc=lambda d: {
            "id": d.name,
            "name": d.supplier_name,
            "supplier_name": d.supplier_name,
            "supplier_type": d.supplier_type,
            "supplier_group": d.supplier_group,
            "country": d.country,
            "email": getattr(d, "email_id", None),
            "phone": getattr(d, "mobile_no", None),
            "disabled": int(getattr(d, "disabled", 0) or 0),
        },
    )


def map_purchase_invoice_row(r: Any) -> dict[str, Any]:
    return {
        "id": r.name,
        "name": r.name,
        "supplier": r.supplier_name or r.supplier,
        "supplier_id": r.supplier,
        "status": r.status,
        "amount": float(r.grand_total or 0),
        "outstanding": float(getattr(r, "outstanding_amount", None) or 0),
        "date": str(r.posting_date) if r.posting_date else None,
        "due_date": str(r.due_date) if getattr(r, "due_date", None) else None,
        "currency": getattr(r, "currency", None),
        "is_return": bool(getattr(r, "is_return", 0)),
        "return_against": getattr(r, "return_against", None),
    }


def map_purchase_invoice_doc(d: Any) -> dict[str, Any]:
    row = map_purchase_invoice_row(d)
    row["items"] = _invoice_items(d)
    row["company"] = d.company
    row["remarks"] = d.remarks
    return row


def list_purchase_invoices(
    page: int | str = 1, page_size: int | str = 20, supplier: str | None = None
) -> dict[str, Any]:
    filters: dict[str, Any] = {"supplier": supplier} if supplier else None
    return _list_doctype(
        "Purchase Invoice",
        fields=[
            "name",
            "supplier",
            "supplier_name",
            "status",
            "grand_total",
            "outstanding_amount",
            "posting_date",
            "due_date",
            "currency",
            "is_return",
            "return_against",
        ],
        page=page,
        page_size=page_size,
        filters=filters,
        order_by="posting_date desc",
        map_row=map_purchase_invoice_row,
    )


def get_purchase_invoice(name: str) -> dict[str, Any]:
    return _get_doctype("Purchase Invoice", name, map_doc=map_purchase_invoice_doc)


def get_document_pdf(doctype: str, name: str, print_format: str | None = None) -> dict[str, Any]:
    """Render a document to PDF via ERPNext's own print engine (frappe.get_print) —
    the accounting engine's authoritative rendering path, never a parallel renderer."""
    import base64

    require_login()
    if not frappe.db.exists(doctype, name):
        frappe.throw(f"{doctype} not found: {name}", frappe.DoesNotExistError)
    require_doc_permission(doctype, "read", name)

    fmt = (print_format or "").strip() or None
    if fmt and not frappe.db.exists("Print Format", fmt):
        fmt = None

    pdf_bytes = frappe.get_print(doctype, name, print_format=fmt, as_pdf=True)
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("utf-8")

    return ok(
        {
            "name": name,
            "print_format": fmt or "Standard",
            "content_type": "application/pdf",
            "filename": f"{name}.pdf",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        },
        meta={"source": "frappe.get_print", "doctype": doctype},
    )


def map_payment_entry_row(r: Any) -> dict[str, Any]:
    return {
        "id": r.name,
        "name": r.name,
        "payment_type": r.payment_type,
        "party_type": r.party_type,
        "party": r.party_name or r.party,
        "party_id": r.party,
        "status": r.status if hasattr(r, "status") else ("Submitted" if r.docstatus == 1 else "Draft"),
        "amount": float(r.paid_amount or 0),
        "date": str(r.posting_date) if r.posting_date else None,
        "mode_of_payment": r.mode_of_payment,
        "docstatus": int(r.docstatus or 0),
    }


def map_payment_entry_doc(d: Any) -> dict[str, Any]:
    row = map_payment_entry_row(d)
    row["references"] = [
        {
            "reference_doctype": ref.reference_doctype,
            "reference_name": ref.reference_name,
            "allocated_amount": float(ref.allocated_amount or 0),
        }
        for ref in (d.references or [])
    ]
    row["company"] = d.company
    row["remarks"] = d.remarks
    return row


def list_payment_entries(
    page: int | str = 1,
    page_size: int | str = 20,
    party_type: str | None = None,
    party: str | None = None,
) -> dict[str, Any]:
    filters: dict[str, Any] | None = None
    if party:
        filters = {"party": party}
        if party_type:
            filters["party_type"] = party_type
    return _list_doctype(
        "Payment Entry",
        fields=[
            "name",
            "payment_type",
            "party_type",
            "party",
            "party_name",
            "paid_amount",
            "posting_date",
            "mode_of_payment",
            "docstatus",
            "status",
        ],
        page=page,
        page_size=page_size,
        filters=filters,
        order_by="posting_date desc",
        map_row=map_payment_entry_row,
    )


def get_payment_entry(name: str) -> dict[str, Any]:
    return _get_doctype("Payment Entry", name, map_doc=map_payment_entry_doc)


def map_journal_entry_row(r: Any) -> dict[str, Any]:
    return {
        "id": r.name,
        "name": r.name,
        "voucher_type": r.voucher_type,
        "title": r.title or r.user_remark or r.name,
        "date": str(r.posting_date) if r.posting_date else None,
        "total_debit": float(r.total_debit or 0),
        "total_credit": float(r.total_credit or 0),
        "docstatus": int(r.docstatus or 0),
        "status": "Submitted" if int(r.docstatus or 0) == 1 else ("Cancelled" if int(r.docstatus or 0) == 2 else "Draft"),
    }


def map_journal_entry_doc(d: Any) -> dict[str, Any]:
    row = map_journal_entry_row(d)
    row["accounts"] = [
        {
            "account": a.account,
            "party_type": a.party_type,
            "party": a.party,
            "cost_center": getattr(a, "cost_center", None),
            "debit": float(a.debit_in_account_currency or 0),
            "credit": float(a.credit_in_account_currency or 0),
            "user_remark": a.user_remark,
        }
        for a in (d.accounts or [])
    ]
    row["company"] = d.company
    row["user_remark"] = d.user_remark
    row["reference_no"] = getattr(d, "cheque_no", None)
    row["reference_date"] = str(d.cheque_date) if getattr(d, "cheque_date", None) else None
    return row


def list_journal_entries(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Journal Entry",
        fields=[
            "name",
            "voucher_type",
            "title",
            "user_remark",
            "posting_date",
            "total_debit",
            "total_credit",
            "docstatus",
        ],
        page=page,
        page_size=page_size,
        map_row=map_journal_entry_row,
    )


def get_journal_entry(name: str) -> dict[str, Any]:
    return _get_doctype("Journal Entry", name, map_doc=map_journal_entry_doc)


def list_accounts(page: int | str = 1, page_size: int | str = 50) -> dict[str, Any]:
    return _list_doctype(
        "Account",
        fields=["name", "account_name", "account_type", "root_type", "company", "is_group"],
        page=page,
        page_size=page_size,
        filters={"is_group": 0},
        order_by="name asc",
        map_row=lambda r: {
            "id": r.name,
            "name": r.name,
            "account_name": r.account_name,
            "account_type": r.account_type,
            "root_type": r.root_type,
            "company": r.company,
        },
    )


def list_chart_of_accounts(company: str | None = None) -> dict[str, Any]:
    """Full Account tree (groups + leaves) for the Chart of Accounts screen.

    Not paginated — a chart of accounts is a tree, not a flat list, and
    fetching a partial page would break the hierarchy. Account counts for a
    single company are small enough (tens to low hundreds) that this is fine.
    """
    require_login()
    require_doc_permission("Account", "read")
    filters: dict[str, Any] = {}
    if company:
        filters["company"] = company
    rows = frappe.get_all(
        "Account",
        filters=filters,
        fields=[
            "name",
            "account_name",
            "account_number",
            "parent_account",
            "account_type",
            "root_type",
            "is_group",
            "disabled",
            "company",
            "account_currency",
        ],
        order_by="lft asc",
        limit_page_length=0,
    )
    data = [
        {
            "id": r.name,
            "name": r.name,
            "account_name": r.account_name or r.name,
            "account_number": r.account_number,
            "parent_account": r.parent_account,
            "account_type": r.account_type,
            "root_type": r.root_type,
            "is_group": int(r.is_group or 0),
            "disabled": int(r.disabled or 0),
            "company": r.company,
            "account_currency": r.account_currency,
        }
        for r in rows
    ]
    return ok(data, meta={"stub": False, "total": len(data), "source": "Account"})


def get_account_balance(account: str, date: str | None = None) -> dict[str, Any]:
    """Current balance for one account, computed by ERPNext — never derived locally."""
    require_login()
    frappe.has_permission("Account", "read", doc=account, throw=True)
    if not frappe.db.exists("Account", account):
        frappe.throw(f"Account {account} not found")
    from erpnext.accounts.utils import get_balance_on

    balance = flt(get_balance_on(account, date=getdate(date) if date else None))
    doc = frappe.get_doc("Account", account)
    debit = balance if balance > 0 else 0.0
    credit = -balance if balance < 0 else 0.0
    return ok(
        {
            "account": account,
            "balance": balance,
            "debit": debit,
            "credit": credit,
            "root_type": doc.root_type,
            "as_of": str(getdate(date)) if date else str(getdate(nowdate())),
        },
        meta={"stub": False, "source": "GL Entry"},
    )


def list_cost_centers(page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    return _list_doctype(
        "Cost Center",
        fields=["name", "cost_center_name", "company", "is_group"],
        page=page,
        page_size=page_size,
        filters={"is_group": 0},
        order_by="name asc",
        map_row=lambda r: {
            "id": r.name,
            "name": r.name,
            "cost_center_name": r.cost_center_name,
            "company": r.company,
        },
    )


# enrich_customer_doc defined earlier (near list_customers)
