"""Go Van — native ERPNext writes with client_id idempotency."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, getdate, nowdate, today

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login, require_str
from zatgo_core.services.erpnext_reads import map_payment_entry_doc, map_sales_invoice_doc
from zatgo_core.services.erpnext_writes import _default_company, _parse_items


_STATUS_MAP = {
    "planned": "Planned",
    "Planned": "Planned",
    "checkedIn": "Checked In",
    "checked_in": "Checked In",
    "Checked In": "Checked In",
    "completed": "Completed",
    "Completed": "Completed",
    "skipped": "Skipped",
    "Skipped": "Skipped",
}


def _find_by_client_id(doctype: str, client_id: str) -> str | None:
    if not client_id or not frappe.db.exists("DocType", doctype):
        return None
    if not frappe.db.has_column(doctype, "zatgo_client_id"):
        return None
    return frappe.db.get_value(doctype, {"zatgo_client_id": client_id}, "name")


def _resolve_customer(customer: str) -> str:
    name = require_str(customer, "customer")
    if frappe.db.exists("Customer", name):
        return name
    found = frappe.db.get_value("Customer", {"customer_name": name}, "name")
    if found:
        return found
    frappe.throw(f"Customer not found: {name}")


def create_order(
    client_id: str,
    customer: str,
    items: Any,
    warehouse: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    require_login()
    cid = require_str(client_id, "client_id")
    existing = _find_by_client_id("Sales Invoice", cid)
    if existing:
        doc = frappe.get_doc("Sales Invoice", existing)
        return ok(
            {**map_sales_invoice_doc(doc), "client_id": cid, "erp_name": doc.name},
            meta={"stub": False, "idempotent": True, "source": "Sales Invoice"},
        )

    frappe.has_permission("Sales Invoice", "create", throw=True)
    party = _resolve_customer(customer)
    if isinstance(items, str):
        import json

        items = json.loads(items)
    if isinstance(items, list):
        normalized = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            if row.get("rate") in (None, "", 0) and row.get("unit_price") is not None:
                row["rate"] = row["unit_price"]
            normalized.append(row)
        items = normalized
    rows = _parse_items(items)

    doc = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": party,
            "company": _default_company(company),
            "posting_date": today(),
            "items": rows,
            "zatgo_client_id": cid,
        }
    )
    wh = (warehouse or "").strip()
    if wh:
        if not frappe.db.exists("Warehouse", wh):
            frappe.throw(f"Warehouse not found: {wh}")
        doc.update_stock = 1
        doc.set_warehouse = wh

    doc.insert()
    doc.submit()
    frappe.db.commit()
    return ok(
        {**map_sales_invoice_doc(doc), "client_id": cid, "erp_name": doc.name},
        meta={"stub": False, "created": True, "submitted": True, "source": "Sales Invoice"},
    )


def create_collection(
    client_id: str,
    customer: str,
    amount: float | str,
    method: str | None = None,
    sales_invoice: str | None = None,
    posting_date: str | None = None,
) -> dict[str, Any]:
    require_login()
    cid = require_str(client_id, "client_id")
    existing = _find_by_client_id("Payment Entry", cid)
    if existing:
        pe = frappe.get_doc("Payment Entry", existing)
        return ok(
            {**map_payment_entry_doc(pe), "client_id": cid, "erp_name": pe.name},
            meta={"stub": False, "idempotent": True, "source": "Payment Entry"},
        )

    frappe.has_permission("Payment Entry", "create", throw=True)
    party = _resolve_customer(customer)
    paid = flt(amount)
    if paid <= 0:
        frappe.throw("Payment amount must be greater than zero")

    si_name = (sales_invoice or "").strip()
    if not si_name:
        # Latest outstanding submitted SI for this customer
        rows = frappe.get_all(
            "Sales Invoice",
            filters={
                "customer": party,
                "docstatus": 1,
                "outstanding_amount": [">", 0],
            },
            fields=["name"],
            order_by="posting_date desc, creation desc",
            limit=1,
        )
        if not rows:
            frappe.throw(f"No outstanding Sales Invoice for customer {party}")
        si_name = rows[0].name

    if not frappe.db.exists("Sales Invoice", si_name):
        frappe.throw(f"Sales Invoice {si_name} not found")

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    pe = get_payment_entry("Sales Invoice", si_name, party_amount=paid)
    pe.posting_date = getdate(posting_date) if posting_date else getdate(nowdate())
    if method:
        pe.mode_of_payment = method
    pe.reference_no = cid
    pe.reference_date = pe.posting_date
    if frappe.db.has_column("Payment Entry", "zatgo_client_id"):
        pe.zatgo_client_id = cid
    pe.insert()
    pe.submit()
    frappe.db.commit()
    return ok(
        {**map_payment_entry_doc(pe), "client_id": cid, "erp_name": pe.name},
        meta={"stub": False, "created": True, "submitted": True, "source": "Payment Entry"},
    )


def list_van_stock(
    warehouse: str,
    page: int | str = 1,
    page_size: int | str = 100,
) -> dict[str, Any]:
    require_login()
    wh = require_str(warehouse, "warehouse")
    if not frappe.db.exists("Warehouse", wh):
        frappe.throw(f"Warehouse not found: {wh}")
    page_i, size_i, start = parse_pagination(page, page_size)
    filt = {"warehouse": wh, "actual_qty": [">", 0]}
    total = frappe.db.count("Bin", filt)
    rows = frappe.get_all(
        "Bin",
        filters=filt,
        fields=["item_code", "warehouse", "actual_qty", "stock_uom", "valuation_rate"],
        order_by="item_code asc",
        start=start,
        page_length=size_i,
    )
    data = []
    for r in rows:
        item_name = frappe.db.get_value("Item", r.item_code, "item_name") or r.item_code
        std_rate = flt(frappe.db.get_value("Item", r.item_code, "standard_rate") or 0)
        rate = std_rate or flt(r.valuation_rate or 0)
        data.append(
            {
                "id": f"{r.item_code}@{r.warehouse}",
                "item_code": r.item_code,
                "item_name": item_name,
                "warehouse": r.warehouse,
                "qty": float(r.actual_qty or 0),
                "uom": r.stock_uom,
                "unit_price": rate,
                "rate": rate,
            }
        )
    payload = paginated(data, page=page_i, page_size=size_i, total=total, sort="item_code asc")
    payload["meta"] = {**payload.get("meta", {}), "stub": False, "source": "Bin", "warehouse": wh}
    return payload


def adjust_stock(
    client_id: str,
    item_code: str,
    delta: float | str,
    warehouse: str,
    company: str | None = None,
) -> dict[str, Any]:
    require_login()
    cid = require_str(client_id, "client_id")
    existing = _find_by_client_id("Stock Entry", cid)
    if existing:
        se = frappe.get_doc("Stock Entry", existing)
        return ok(
            {
                "name": se.name,
                "erp_name": se.name,
                "client_id": cid,
                "item_code": item_code,
                "delta": flt(delta),
            },
            meta={"stub": False, "idempotent": True, "source": "Stock Entry"},
        )

    frappe.has_permission("Stock Entry", "create", throw=True)
    code = require_str(item_code, "item_code")
    wh = require_str(warehouse, "warehouse")
    qty = flt(delta)
    if qty == 0:
        frappe.throw("delta must not be zero")
    if not frappe.db.exists("Item", code):
        frappe.throw(f"Item not found: {code}")
    if not frappe.db.exists("Warehouse", wh):
        frappe.throw(f"Warehouse not found: {wh}")

    purpose = "Material Receipt" if qty > 0 else "Material Issue"
    abs_qty = abs(qty)
    row: dict[str, Any] = {
        "item_code": code,
        "qty": abs_qty,
    }
    if qty > 0:
        row["t_warehouse"] = wh
    else:
        row["s_warehouse"] = wh

    se = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": purpose,
            "purpose": purpose,
            "company": _default_company(company),
            "items": [row],
            "zatgo_client_id": cid,
        }
    )
    se.insert()
    se.submit()
    frappe.db.commit()
    return ok(
        {
            "name": se.name,
            "erp_name": se.name,
            "client_id": cid,
            "item_code": code,
            "delta": qty,
            "warehouse": wh,
        },
        meta={"stub": False, "created": True, "submitted": True, "source": "Stock Entry"},
    )


def update_visit(
    client_id: str,
    stop_id: str,
    visit_status: str,
) -> dict[str, Any]:
    require_login()
    cid = require_str(client_id, "client_id")
    name = require_str(stop_id, "stop_id")
    if not frappe.db.exists("ZG Trip", name):
        frappe.throw(f"ZG Trip {name} not found")
    status = _STATUS_MAP.get(str(visit_status).strip())
    if not status:
        frappe.throw(f"Invalid visit_status: {visit_status}")

    frappe.has_permission("ZG Trip", "write", doc=name, throw=True)
    doc = frappe.get_doc("ZG Trip", name)
    doc.status = status
    if frappe.db.has_column("ZG Trip", "zatgo_client_id"):
        doc.zatgo_client_id = cid
    doc.save()
    frappe.db.commit()
    return ok(
        {
            "name": doc.name,
            "erp_name": doc.name,
            "client_id": cid,
            "id": doc.name,
            "status": doc.status,
            "customer": doc.customer,
            "address": doc.address,
            "sequence": doc.sequence,
            "lat": doc.lat,
            "lng": doc.lng,
        },
        meta={"stub": False, "updated": True, "source": "ZG Trip"},
    )
