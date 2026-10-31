"""Resto POS back-office: profile, menu items, stock, payments, customers, dashboard.

Everything here composes ERPNext documents (Item, Stock Entry, Customer, Sales
Invoice / Payment Entry read-only) -- no parallel ledgers. Stock changes are a
real Stock Entry (Material Receipt / Material Issue) keyed on
`zatgo_client_id`, so a retried request never posts twice.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt, today

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login, require_str

_MODE_TO_KEY = {"cash": "cash", "card": "card", "wallet": "wallet"}
_OPEN_ORDER_STATUSES = ("Open", "Sent", "Ready")


def _company(company: str | None = None) -> str:
    from zatgo_core.services.resto_pos_service import _default_company

    return _default_company(company)


def _warehouse(company: str) -> str:
    from zatgo_core.services.resto_pos_service import _resolve_pos_warehouse

    return _resolve_pos_warehouse(company)


# --- profile -------------------------------------------------------------


def get_profile() -> dict[str, Any]:
    """What this site offers the POS: enabled industries, restaurant features,
    company / currency and payment modes. Not industry-gated, so the POS can
    still learn that Restaurant is switched off."""
    from zatgo_core.industries import gate, registry
    from zatgo_core.services import pos_settings

    require_login()
    enabled = sorted(gate.enabled_keys())
    restaurant = registry.get("restaurant")
    restaurant_on = "restaurant" in enabled
    retail_on = "supermarket" in enabled
    # The POS Type of ZG POS Settings decides; with none chosen the industries do (Restaurant wins when both are on).
    pos_mode = pos_settings.pos_mode(set(enabled))
    try:
        company = _company()
    except Exception:
        company = None
    currency = (
        frappe.get_cached_value("Company", company, "default_currency") if company else None
    )
    modes = frappe.get_all("Mode of Payment", filters={"enabled": 1}, pluck="name", order_by="name asc")
    tax: dict[str, Any] = {"tax_template": None, "tax_rate": 0.0, "tax_inclusive": 0}
    if company:
        from zatgo_core.services.vansalex_settings import tax_summary

        tax = tax_summary(company)
    return ok(
        {
            # The invoice's tax comes from the company's Sales Taxes template (the
            # POS only displays it): percent on net total, and whether prices include it.
            "tax_template": tax["tax_template"],
            "tax_rate": tax["tax_rate"],
            "tax_inclusive": tax["tax_inclusive"],
            "industries": enabled,
            "restaurant": restaurant_on,
            "retail": retail_on,
            "pos_mode": pos_mode,
            "pos_type": pos_settings.pos_type(set(enabled)),
            "pos_vertical": pos_settings.pos_vertical(set(enabled)),
            "features": list(restaurant.features) if restaurant and restaurant_on else [],
            "company": company,
            "currency": currency,
            "payment_modes": modes,
            "user": frappe.session.user,
        },
        meta={"stub": False, "source": "ZG System Settings"},
    )


# --- menu items ------------------------------------------------------------


def _leaf_item_group() -> str:
    found = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
    if found:
        return found
    frappe.throw("No leaf Item Group exists. Create an Item Group first.")


def upsert_item(
    item_code: str | None = None,
    item_name: str | None = None,
    price: float | str | None = None,
    item_group: str | None = None,
    barcode: str | None = None,
    uom: str | None = None,
    enabled: int | str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import get_item

    require_login()
    code = (item_code or "").strip()
    if code and frappe.db.exists("Item", code):
        frappe.has_permission("Item", "write", doc=code, throw=True)
        doc = frappe.get_doc("Item", code)
    else:
        frappe.has_permission("Item", "create", throw=True)
        name = require_str(item_name, "item_name")
        doc = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code or name,
                "item_name": name,
                "item_group": (item_group or "").strip() or _leaf_item_group(),
                "stock_uom": (uom or "").strip() or "Nos",
                "is_stock_item": 1,
                "is_sales_item": 1,
            }
        )
    if item_name and doc.get("name"):
        doc.item_name = item_name.strip()
    if item_group and (item_group or "").strip():
        doc.item_group = item_group.strip()
    if price is not None and price != "":
        doc.standard_rate = flt(price)
    if enabled is not None and enabled != "":
        doc.disabled = 0 if cint(enabled) else 1
    if barcode is not None and (barcode or "").strip():
        code_bc = barcode.strip()
        if not any(b.barcode == code_bc for b in doc.get("barcodes") or []):
            doc.append("barcodes", {"barcode": code_bc})
    doc.save()
    return get_item(doc.name)


def disable_item(item_code: str) -> dict[str, Any]:
    require_login()
    code = require_str(item_code, "item_code")
    frappe.has_permission("Item", "write", doc=code, throw=True)
    doc = frappe.get_doc("Item", code)
    doc.disabled = 1
    doc.save()
    return ok({"id": doc.name, "disabled": 1}, meta={"stub": False, "source": "Item"})


def find_by_barcode(code: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import get_item

    require_login()
    value = require_str(code, "code")
    item = frappe.db.get_value("Item Barcode", {"barcode": value}, "parent")
    if not item:
        item = frappe.db.get_value("Item", {"name": value, "disabled": 0}, "name")
    if not item:
        return ok(None, meta={"stub": False, "found": False})
    return get_item(item)


# --- stock -----------------------------------------------------------------


def _stock_rows(company: str, warehouse: str | None) -> list[dict[str, Any]]:
    wh_filter = [warehouse] if warehouse else frappe.get_all(
        "Warehouse", filters={"company": company, "disabled": 0, "is_group": 0}, pluck="name"
    )
    if not wh_filter:
        return []
    on_hand: dict[str, float] = {}
    for b in frappe.get_all(
        "Bin", filters={"warehouse": ("in", wh_filter)}, fields=["item_code", "actual_qty"]
    ):
        on_hand[b.item_code] = on_hand.get(b.item_code, 0.0) + flt(b.actual_qty)
    items = frappe.get_all(
        "Item",
        filters={"disabled": 0, "is_stock_item": 1},
        fields=["name", "item_name", "stock_uom", "item_group"],
        order_by="item_name asc",
    )
    reorder = {
        r.parent: flt(r.warehouse_reorder_level)
        for r in frappe.get_all(
            "Item Reorder",
            filters={"warehouse": ("in", wh_filter), "parenttype": "Item"},
            fields=["parent", "warehouse_reorder_level"],
        )
    }
    return [
        {
            "id": i.name,
            "name": i.item_name or i.name,
            "unit": i.stock_uom or "Nos",
            "onHand": on_hand.get(i.name, 0.0),
            "reorderAt": reorder.get(i.name, 0.0),
            "category": i.item_group or "",
        }
        for i in items
    ]


def list_stock(
    warehouse: str | None = None,
    page: int | str = 1,
    page_size: int | str = 100,
    company: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Bin", "read", throw=True)
    page_i, size_i, start = parse_pagination(page, page_size)
    rows = _stock_rows(_company(company), (warehouse or "").strip() or None)
    q = (search or "").strip().lower()
    if q:
        rows = [r for r in rows if q in r["id"].lower() or q in r["name"].lower()]
    return paginated(
        rows[start : start + size_i],
        page=page_i,
        page_size=size_i,
        total=len(rows),
        sort="item_name asc",
    )


def adjust_stock(
    item_code: str,
    qty: float | str,
    client_id: str,
    warehouse: str | None = None,
    reason: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    """Add (qty > 0, Material Receipt) or remove (qty < 0, Material Issue) stock.
    Idempotent on `client_id`."""
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    code = require_str(item_code, "item_code")
    cid = require_str(client_id, "client_id")
    delta = flt(qty)
    if not delta:
        frappe.throw("Quantity must not be zero.")

    existing = find_by_client_id("Stock Entry", cid)
    if existing:
        return ok(_stock_ack(existing, code), meta={"stub": False, "idempotent": True})

    frappe.has_permission("Stock Entry", "create", throw=True)
    if not frappe.db.exists("Item", code):
        frappe.throw(f"Item {code} does not exist.")
    comp = _company(company)
    wh = (warehouse or "").strip() or _warehouse(comp)

    line: dict[str, Any] = {"item_code": code, "qty": abs(delta)}
    if delta > 0:
        entry_type = "Material Receipt"
        line["t_warehouse"] = wh
        rate = flt(frappe.db.get_value("Item", code, "valuation_rate")) or flt(
            frappe.db.get_value("Item", code, "last_purchase_rate")
        ) or flt(frappe.db.get_value("Item", code, "standard_rate"))
        line["basic_rate"] = rate
        line["allow_zero_valuation_rate"] = 0 if rate else 1
    else:
        entry_type = "Material Issue"
        line["s_warehouse"] = wh

    doc = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": entry_type,
            "purpose": entry_type,
            "company": comp,
            "remarks": (reason or "").strip() or "Resto POS stock adjustment",
            "items": [line],
            "zatgo_client_id": cid,
        }
    )
    doc, created = insert_idempotent(doc, doctype="Stock Entry", client_id=cid)
    if created:
        doc.submit()
    return ok(_stock_ack(doc.name, code), meta={"stub": False, "idempotent": not created})


def _stock_ack(stock_entry: str, item_code: str) -> dict[str, Any]:
    qty = sum(flt(q) for q in frappe.get_all("Bin", filters={"item_code": item_code}, pluck="actual_qty"))
    return {"stock_entry": stock_entry, "item_code": item_code, "onHand": qty}


# --- payments --------------------------------------------------------------


def list_payments(
    date: str | None = None, page: int | str = 1, page_size: int | str = 100
) -> dict[str, Any]:
    """Paid POS orders (with their Sales Invoice / Payment Entry), newest first.
    `date` (YYYY-MM-DD) limits to one posting day."""
    from zatgo_core.services.resto_pos_service import _map_payment_record

    require_login()
    frappe.has_permission("ZG Order", "read", throw=True)
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: dict[str, Any] = {"status": "Paid", "sales_invoice": ("is", "set")}
    orders = frappe.get_all(
        "ZG Order",
        filters=filters,
        fields=["name", "order_number", "channel", "sales_invoice", "payment_entry"],
        order_by="modified desc",
    )
    out: list[dict[str, Any]] = []
    for o in orders:
        si = frappe.db.get_value(
            "Sales Invoice", o.sales_invoice, ["name", "grand_total", "posting_date", "docstatus"], as_dict=True
        )
        if not si or si.docstatus != 1:
            continue
        if date and str(si.posting_date) != date:
            continue
        method_key = "cash"
        pe = None
        if o.payment_entry:
            pe = frappe.db.get_value(
                "Payment Entry", o.payment_entry, ["name", "mode_of_payment", "posting_date"], as_dict=True
            )
            if pe:
                method_key = _MODE_TO_KEY.get((pe.mode_of_payment or "").lower(), "cash")
        out.append(_map_payment_record(o, si, pe, method_key))
    total = len(out)
    return paginated(
        out[start : start + size_i],
        page=page_i,
        page_size=size_i,
        total=total,
        sort="modified desc",
    )


# --- customers -------------------------------------------------------------


def _map_customer(row: Any) -> dict[str, Any]:
    return {
        "id": row.get("name"),
        "name": row.get("customer_name") or row.get("name"),
        "phone": row.get("mobile_no") or "",
        "email": row.get("email_id") or "",
    }


def list_customers(search: str | None = None, page: int | str = 1, page_size: int | str = 50) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Customer", "read", throw=True)
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: list[Any] = [["disabled", "=", 0]]
    q = (search or "").strip()
    or_filters = (
        [["customer_name", "like", f"%{q}%"], ["mobile_no", "like", f"%{q}%"]] if q else None
    )
    total = len(frappe.get_all("Customer", filters=filters, or_filters=or_filters, pluck="name"))
    rows = frappe.get_all(
        "Customer",
        filters=filters,
        or_filters=or_filters,
        fields=["name", "customer_name", "mobile_no", "email_id"],
        order_by="customer_name asc",
        start=start,
        page_length=size_i,
    )
    return paginated(
        [_map_customer(r) for r in rows],
        page=page_i,
        page_size=size_i,
        total=total,
        sort="customer_name asc",
    )


def upsert_customer(
    customer_id: str | None = None,
    customer_name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_writes import create_customer

    require_login()
    cid = (customer_id or "").strip()
    if cid and frappe.db.exists("Customer", cid):
        frappe.has_permission("Customer", "write", doc=cid, throw=True)
        doc = frappe.get_doc("Customer", cid)
        if customer_name and customer_name.strip():
            doc.customer_name = customer_name.strip()
        doc.save()
        # mobile_no / email_id are fetched-from-contact fields: a plain save keeps
        # the fetched value, so write them directly (same as create_customer).
        if phone is not None:
            doc.db_set("mobile_no", phone.strip() or None)
        if email is not None:
            doc.db_set("email_id", email.strip() or None)
        return ok(_map_customer(doc), meta={"stub": False, "source": "Customer"})
    created = create_customer(
        customer_name=require_str(customer_name, "customer_name"),
        customer_type="Individual",
        email=email,
        phone=phone,
        client_id=client_id,
    )
    data = created["data"]
    name = data.get("id") or data.get("name")
    return ok(_map_customer(frappe.get_doc("Customer", name)), meta={"stub": False, "source": "Customer"})


# --- dashboard -------------------------------------------------------------


def dashboard_counts() -> dict[str, Any]:
    require_login()
    frappe.has_permission("ZG Order", "read", throw=True)
    tables = {"Free": 0, "Occupied": 0, "Billing": 0}
    for status in tables:
        tables[status] = frappe.db.count("ZG Table", {"status": status})
    open_orders = frappe.db.count("ZG Order", {"status": ("in", _OPEN_ORDER_STATUSES)})

    low = 0
    try:
        rows = _stock_rows(_company(), None)
        low = sum(1 for r in rows if r["reorderAt"] and r["onHand"] <= r["reorderAt"])
    except Exception:
        # No warehouse configured yet: nothing to report, not an error for the dashboard.
        frappe.clear_last_message()

    sales = 0.0
    n = 0
    for o in frappe.get_all(
        "ZG Order",
        filters={"status": "Paid", "sales_invoice": ("is", "set")},
        fields=["sales_invoice"],
    ):
        si = frappe.db.get_value(
            "Sales Invoice", o.sales_invoice, ["grand_total", "posting_date", "docstatus"], as_dict=True
        )
        if si and si.docstatus == 1 and str(si.posting_date) == today():
            sales += flt(si.grand_total)
            n += 1
    return ok(
        {
            "freeTables": tables["Free"],
            "occupiedTables": tables["Occupied"] + tables["Billing"],
            "openOrders": open_orders,
            "lowStock": low,
            "todaySales": sales,
            "paymentsToday": n,
            "revenueToday": sales,
        },
        meta={"stub": False, "source": "ZG Order"},
    )
