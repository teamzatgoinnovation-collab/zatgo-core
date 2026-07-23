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


def _company_tax_settings(company: str) -> tuple[str | None, bool]:
    """Return (default_tax_template, tax_inclusive) for company."""
    if not frappe.db.exists("DocType", "ZG Company Settings"):
        return None, False
    row = frappe.db.get_value(
        "ZG Company Settings",
        {"company": company},
        ["default_tax_template", "enable_tax_inclusive"],
        as_dict=True,
    )
    if not row:
        return None, False
    template = (row.get("default_tax_template") or "").strip() or None
    inclusive = bool(int(row.get("enable_tax_inclusive") or 0))
    return template, inclusive


def _apply_sales_taxes(doc: Any, company: str) -> None:
    template, inclusive = _company_tax_settings(company)
    if not template:
        # Fallback: first enabled Sales Taxes and Charges Template for company
        if frappe.db.exists("DocType", "Sales Taxes and Charges Template"):
            template = frappe.db.get_value(
                "Sales Taxes and Charges Template",
                {"company": company, "disabled": 0},
                "name",
            )
    if not template or not frappe.db.exists("Sales Taxes and Charges Template", template):
        return
    doc.taxes_and_charges = template
    try:
        from erpnext.controllers.accounts_controller import get_taxes_and_charges

        doc.set("taxes", [])
        for tax in get_taxes_and_charges("Sales Taxes and Charges Template", template):
            row = dict(tax)
            # When company prices are tax-inclusive, force included_in_print_rate
            # so ERPNext does not add VAT on top of already-inclusive rates.
            if inclusive:
                row["included_in_print_rate"] = 1
            doc.append("taxes", row)
    except Exception:
        # Older / alternate API
        try:
            doc.append_taxes_from_master()
            if inclusive:
                for tax in doc.taxes or []:
                    tax.included_in_print_rate = 1
        except Exception:
            frappe.log_error(title="VanSale tax template apply failed", message=frappe.get_traceback())


def _ack_sales_invoice(doc: Any, cid: str, *, idempotent: bool, created: bool) -> dict[str, Any]:
    from zatgo_core.setup.ensure_print_formats import PRINT_FORMAT_NAME

    return ok(
        {
            **map_sales_invoice_doc(doc),
            "client_id": cid,
            "erp_name": doc.name,
            "print_format": PRINT_FORMAT_NAME,
            "docstatus": int(doc.docstatus or 0),
        },
        meta={
            "stub": False,
            "idempotent": idempotent,
            "created": created,
            "submitted": int(doc.docstatus or 0) == 1,
            "source": "Sales Invoice",
        },
    )


def _ensure_submitted_sales_invoice(
    doc: Any,
    *,
    warehouse: str | None = None,
) -> Any:
    """Submit draft SI from a prior failed attempt; only succeed when docstatus=1."""
    status = int(doc.docstatus or 0)
    if status == 2:
        frappe.throw(
            f"Sales Invoice {doc.name} was cancelled. Create a new sale with a new client_id.",
            frappe.ValidationError,
        )
    if status == 1:
        return doc

    wh = (warehouse or "").strip()
    if wh:
        if not frappe.db.exists("Warehouse", wh):
            frappe.throw(f"Warehouse not found: {wh}")
        if not doc.set_warehouse:
            doc.update_stock = 1
            doc.set_warehouse = wh
            doc.save()

    if not doc.update_stock or not (doc.set_warehouse or "").strip():
        frappe.throw(
            f"Sales Invoice {doc.name} is still a draft without van warehouse / update_stock. "
            "Set warehouse on the van profile and retry sync.",
            frappe.ValidationError,
        )

    try:
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.throw(
            f"Sales Invoice {doc.name} exists as draft but could not be submitted. "
            "Fix stock/accounts, then retry sync.",
            frappe.ValidationError,
        )
    doc.reload()
    if int(doc.docstatus or 0) != 1:
        frappe.throw(
            f"Sales Invoice {doc.name} is not submitted (docstatus={doc.docstatus}).",
            frappe.ValidationError,
        )
    return doc


def create_order(
    client_id: str,
    customer: str,
    items: Any,
    warehouse: str | None = None,
    company: str | None = None,
    trip_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.zatca_qr import generate_and_store_zatca_qr

    require_login()
    cid = require_str(client_id, "client_id")
    wh = (warehouse or "").strip()

    existing = _find_by_client_id("Sales Invoice", cid)
    if existing:
        doc = frappe.get_doc("Sales Invoice", existing)
        doc = _ensure_submitted_sales_invoice(doc, warehouse=wh or None)
        try:
            generate_and_store_zatca_qr(doc)
            frappe.db.commit()
            doc.reload()
        except Exception:
            frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())
        return _ack_sales_invoice(doc, cid, idempotent=True, created=False)

    if not wh:
        frappe.throw(
            "Van warehouse is required to create a stock-updating Sales Invoice.",
            frappe.ValidationError,
        )
    if not frappe.db.exists("Warehouse", wh):
        frappe.throw(f"Warehouse not found: {wh}")

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

    company_name = _default_company(company)
    # Prefer customer default price list when item rates missing
    pl = frappe.db.get_value("Customer", party, "default_price_list")
    if pl:
        for row in rows:
            if flt(row.get("rate") or 0) <= 0:
                rate = frappe.db.get_value(
                    "Item Price",
                    {"item_code": row.get("item_code"), "price_list": pl},
                    "price_list_rate",
                )
                if rate is not None:
                    row["rate"] = flt(rate)

    doc = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": party,
            "company": company_name,
            "posting_date": today(),
            "items": rows,
            "zatgo_client_id": cid,
            "update_stock": 1,
            "set_warehouse": wh,
        }
    )
    if pl and frappe.get_meta("Sales Invoice").has_field("selling_price_list"):
        doc.selling_price_list = pl

    _apply_sales_taxes(doc, company_name)

    doc.insert()
    try:
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.throw(
            "Could not create and submit Sales Invoice. Fix stock/accounts, then retry sync.",
            frappe.ValidationError,
        )

    try:
        generate_and_store_zatca_qr(doc)
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())

    trip = (trip_id or "").strip()
    if trip and frappe.db.exists("ZG Trip", trip) and frappe.db.has_column("ZG Trip", "sales_invoice"):
        try:
            frappe.db.set_value("ZG Trip", trip, "sales_invoice", doc.name, update_modified=False)
            frappe.db.commit()
        except Exception:
            frappe.log_error(title="VanSale trip-SI link failed", message=frappe.get_traceback())

    doc.reload()
    payload = _ack_sales_invoice(doc, cid, idempotent=False, created=True)
    payload["data"]["trip_id"] = trip or None
    return payload



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


def transfer_stock(
    client_id: str,
    item_code: str,
    qty: float | str,
    from_warehouse: str,
    to_warehouse: str,
    company: str | None = None,
) -> dict[str, Any]:
    """Material Transfer between warehouses (e.g. main WH → van WH)."""
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
                "qty": flt(qty),
                "from_warehouse": from_warehouse,
                "to_warehouse": to_warehouse,
            },
            meta={"stub": False, "idempotent": True, "source": "Stock Entry"},
        )

    frappe.has_permission("Stock Entry", "create", throw=True)
    code = require_str(item_code, "item_code")
    src = require_str(from_warehouse, "from_warehouse")
    dst = require_str(to_warehouse, "to_warehouse")
    amount = flt(qty)
    if amount <= 0:
        frappe.throw("qty must be greater than zero")
    if src == dst:
        frappe.throw("from_warehouse and to_warehouse must differ")
    if not frappe.db.exists("Item", code):
        frappe.throw(f"Item not found: {code}")
    if not frappe.db.exists("Warehouse", src):
        frappe.throw(f"Warehouse not found: {src}")
    if not frappe.db.exists("Warehouse", dst):
        frappe.throw(f"Warehouse not found: {dst}")

    se = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Transfer",
            "purpose": "Material Transfer",
            "company": _default_company(company),
            "items": [
                {
                    "item_code": code,
                    "qty": amount,
                    "s_warehouse": src,
                    "t_warehouse": dst,
                }
            ],
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
            "qty": amount,
            "from_warehouse": src,
            "to_warehouse": dst,
        },
        meta={"stub": False, "created": True, "submitted": True, "source": "Stock Entry"},
    )


def update_visit(
    client_id: str,
    stop_id: str,
    visit_status: str,
    lat: float | str | None = None,
    lng: float | str | None = None,
    notes: str | None = None,
    no_sale_reason: str | None = None,
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
    if lat is not None and str(lat) != "" and frappe.db.has_column("ZG Trip", "check_in_lat"):
        doc.check_in_lat = flt(lat)
    if lng is not None and str(lng) != "" and frappe.db.has_column("ZG Trip", "check_in_lng"):
        doc.check_in_lng = flt(lng)
    if status == "Checked In" and frappe.db.has_column("ZG Trip", "check_in_at"):
        from frappe.utils import now_datetime

        doc.check_in_at = now_datetime()
    if notes is not None and frappe.db.has_column("ZG Trip", "visit_notes"):
        doc.visit_notes = notes
    if no_sale_reason is not None and frappe.db.has_column("ZG Trip", "no_sale_reason"):
        doc.no_sale_reason = no_sale_reason
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
            "check_in_lat": getattr(doc, "check_in_lat", None),
            "check_in_lng": getattr(doc, "check_in_lng", None),
            "sales_invoice": getattr(doc, "sales_invoice", None),
        },
        meta={"stub": False, "updated": True, "source": "ZG Trip"},
    )
