"""List/get helpers over ERPNext core DocTypes for zatgo_core product endpoints."""

from __future__ import annotations

from typing import Any

import frappe

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
        "category": row.get("item_group"),
        "price": float(row.get("standard_rate") or 0),
        "rate": float(row.get("standard_rate") or 0),
        "station": "counter",
        "available": 1 if row.get("disabled") in (0, "0", None, False) else 0,
        "sku": row.get("name"),
        "barcode": row.get("barcode") or "",
        "uom": row.get("stock_uom"),
        "verticals": [],
    }


def list_items(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Item",
        fields=[
            "name",
            "item_name",
            "item_group",
            "standard_rate",
            "stock_uom",
            "disabled",
        ],
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
        return map_item_row(
            {
                "name": doc.name,
                "item_name": doc.item_name,
                "item_group": doc.item_group,
                "standard_rate": doc.standard_rate,
                "stock_uom": doc.stock_uom,
                "disabled": doc.disabled,
                "barcode": barcode,
            }
        )

    return _get_doctype("Item", name, map_doc=map_doc)


def list_customers(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Customer",
        fields=["name", "customer_name", "customer_type", "territory", "disabled"],
        page=page,
        page_size=page_size,
        filters={"disabled": 0},
        map_row=lambda r: {
            "id": r.name,
            "name": r.customer_name or r.name,
            "customer_name": r.customer_name,
            "customer_type": r.customer_type,
            "territory": r.territory,
        },
    )


def get_customer(name: str) -> dict[str, Any]:
    return _get_doctype(
        "Customer",
        name,
        map_doc=lambda d: {
            "id": d.name,
            "name": d.customer_name,
            "customer_name": d.customer_name,
            "customer_type": d.customer_type,
            "territory": d.territory,
        },
    )


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


def list_sales_invoices(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return _list_doctype(
        "Sales Invoice",
        fields=["name", "customer", "customer_name", "status", "grand_total", "posting_date"],
        page=page,
        page_size=page_size,
        map_row=lambda r: {
            "id": r.name,
            "name": r.name,
            "customer": r.customer_name or r.customer,
            "status": r.status,
            "amount": float(r.grand_total or 0),
            "date": str(r.posting_date) if r.posting_date else None,
        },
    )


def get_sales_invoice(name: str) -> dict[str, Any]:
    return _get_doctype(
        "Sales Invoice",
        name,
        map_doc=lambda d: {
            "id": d.name,
            "name": d.name,
            "customer": d.customer_name or d.customer,
            "status": d.status,
            "amount": float(d.grand_total or 0),
            "date": str(d.posting_date) if d.posting_date else None,
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
