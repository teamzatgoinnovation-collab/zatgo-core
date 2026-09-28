"""Resto POS: tables, orders, and checkout/payment.

Orders and tables are plain state doctypes (no GL/stock impact) — same
pattern as `ZG KDS Ticket`. Checkout is where this domain touches real
money: `pay()` builds and submits a Sales Invoice (reusing
`vansalex_service._apply_sales_taxes` and the same update_stock/
set_warehouse pattern vansalex already uses in production) and a Payment
Entry, both keyed on `zatgo_client_id` via `insert_idempotent` — no
parallel accounting logic, only composition of what `erpnext_writes.py`
and `vansalex_service.py` already do.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, get_fullname, now_datetime, today

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login, require_str

_ORDER_STATUS_FLOW = ("Open", "Sent", "Ready", "Paid", "Void")
_TABLE_STATUS_MAP = {"free": "Free", "occupied": "Occupied", "billing": "Billing"}
_ORDER_CHANNEL_MAP = {
    "dine_in": "Dine In",
    "counter": "Counter",
    "walk_in": "Walk In",
    "delivery": "Delivery",
}
_MODE_OF_PAYMENT_MAP = {"cash": "Cash", "card": "Card", "wallet": "Wallet"}
_STATIONS = ("grill", "cold", "bar", "dessert", "counter")
_ITEM_STATUS_FLOW = ("Queued", "Preparing", "Ready", "Served")


# --- mapping -------------------------------------------------------------


def _map_order_item(row: Any) -> dict[str, Any]:
    r = row if isinstance(row, dict) else row.as_dict()
    extras_raw = (r.get("extras") or "").strip()
    extras = (
        [{"id": e, "name": e, "price": 0} for e in extras_raw.split(",") if e.strip()]
        if extras_raw
        else []
    )
    return {
        "id": r.get("name"),
        "name": r.get("item_name") or r.get("item_code"),
        "qty": float(r.get("qty") or 0),
        "price": float(r.get("rate") or 0),
        "station": (r.get("station") or "grill").lower(),
        "status": (r.get("status") or "Queued").lower(),
        "extras": extras,
    }


def _map_order_doc(doc: Any, items: list[Any] | None = None) -> dict[str, Any]:
    delivery = None
    if doc.channel == "Delivery" or doc.delivery_address or doc.delivery_boy:
        delivery = {
            "address": doc.delivery_address or "",
            "phone": doc.delivery_phone or "",
            "notes": doc.delivery_notes or None,
            "deliveryBoyId": doc.delivery_boy or None,
            "deliveryBoyName": doc.delivery_boy_name or None,
        }
    row_items = items if items is not None else (doc.items or [])
    return {
        "id": doc.name,
        "number": doc.order_number,
        "tableId": doc.table or None,
        "tableName": doc.table_name or "",
        "covers": int(doc.covers or 1),
        "status": (doc.status or "Open").lower(),
        "items": [_map_order_item(row) for row in row_items],
        "openedAt": str(doc.opened_at or ""),
        "server": doc.server or "",
        "channel": (doc.channel or "Counter").lower().replace(" ", "_"),
        "note": doc.note or None,
        "customerId": doc.customer or None,
        "customerName": doc.customer_name or None,
        "customerPhone": doc.customer_phone or None,
        "delivery": delivery,
        "deliveryStatus": (
            (doc.delivery_status or "").lower().replace(" ", "_") or None
        ),
        "sales_invoice": doc.sales_invoice or None,
        "payment_entry": doc.payment_entry or None,
    }


def _map_table_doc(doc: Any) -> dict[str, Any]:
    """`doc` is either a `ZG Table` Document or a `frappe.get_all` row dict —
    both support `.get(fieldname)`."""
    return {
        "id": doc.get("table_code"),
        "name": doc.get("table_name"),
        "seats": int(doc.get("seats") or 0),
        "zone": doc.get("zone") or "",
        "status": (doc.get("status") or "Free").lower(),
        "orderId": doc.get("current_order") or None,
        "covers": int(doc.get("covers") or 0),
    }


# --- resolution helpers ----------------------------------------------------


def _resolve_pos_warehouse(company: str) -> str:
    if frappe.db.exists("DocType", "ZG Company Settings"):
        wh = frappe.db.get_value("ZG Company Settings", {"company": company}, "default_warehouse")
        if wh and frappe.db.exists("Warehouse", wh):
            return wh
    wh = frappe.db.get_value(
        "Warehouse", {"company": company, "disabled": 0, "is_group": 0}, "name"
    )
    if wh:
        return wh
    frappe.throw(
        f"No warehouse configured for company {company}. "
        "Set ZG Company Settings.default_warehouse or create a Warehouse."
    )


def _resolve_pos_customer(
    customer_id: str | None, customer_name: str | None, customer_phone: str | None
) -> str:
    from zatgo_core.services.erpnext_writes import create_customer

    cid = (customer_id or "").strip()
    if cid and frappe.db.exists("Customer", cid):
        return cid

    name = (customer_name or "").strip()
    if name:
        found = frappe.db.get_value("Customer", {"customer_name": name}, "name")
        if found:
            return found
        created = create_customer(customer_name=name, phone=customer_phone)
        return created["data"]["id"]

    existing = frappe.db.get_value("Customer", {"customer_name": "Walk-in Customer"}, "name")
    if existing:
        return existing
    created = create_customer(customer_name="Walk-in Customer")
    return created["data"]["id"]


def _default_company(company: str | None = None) -> str:
    from zatgo_core.services.erpnext_writes import _default_company as _dc

    return _dc(company)


# --- orders ----------------------------------------------------------------


def _next_order_number() -> str:
    return f"ORD-{frappe.generate_hash(length=6).upper()}"


def _parse_order_items(items: Any) -> list[dict[str, Any]]:
    if items is None:
        return []
    if isinstance(items, str):
        import json

        items = json.loads(items)
    if not isinstance(items, list):
        frappe.throw("items must be a list")
    rows: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            frappe.throw("Each item must be an object")
        item_code = require_str(raw.get("item_code") or raw.get("productId"), "item_code")
        qty = flt(raw.get("qty") or 1)
        if qty <= 0:
            frappe.throw("Item qty must be greater than zero")
        rate = flt(raw.get("rate") if raw.get("rate") is not None else raw.get("price") or 0)
        station = str(raw.get("station") or "grill").lower()
        if station not in _STATIONS:
            station = "grill"
        extras_raw = raw.get("extras")
        extras = ""
        if isinstance(extras_raw, list):
            extras = ",".join(
                str(e.get("name") if isinstance(e, dict) else e).strip()
                for e in extras_raw
                if e
            )
        rows.append(
            {
                "item_code": item_code,
                "item_name": raw.get("item_name") or raw.get("name") or item_code,
                "qty": qty,
                "rate": rate,
                "station": station,
                "status": "Queued",
                "extras": extras,
                "kds_synced": 0,
            }
        )
    return rows


def create_order(
    table: str | None = None,
    covers: int | str = 1,
    channel: str = "counter",
    items: Any = None,
    note: str | None = None,
    customer_id: str | None = None,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    delivery: Any = None,
    company: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("ZG Order", cid)
        if existing:
            doc = frappe.get_doc("ZG Order", existing)
            return ok(
                _map_order_doc(doc),
                meta={"stub": False, "idempotent": True, "source": "ZG Order"},
            )

    frappe.has_permission("ZG Order", "create", throw=True)

    table_doc = None
    table_name = ""
    if table:
        if not frappe.db.exists("ZG Table", table):
            frappe.throw(f"ZG Table {table} not found")
        table_doc = frappe.get_doc("ZG Table", table)
        table_name = table_doc.table_name

    comp = _default_company(company or (table_doc.company if table_doc else None))
    channel_key = str(channel or "counter").lower().replace(" ", "_")
    channel_label = _ORDER_CHANNEL_MAP.get(channel_key, "Counter")

    delivery_dict = delivery if isinstance(delivery, dict) else {}

    doc = frappe.get_doc(
        {
            "doctype": "ZG Order",
            "order_number": _next_order_number(),
            "table": table_doc.name if table_doc else None,
            "table_name": table_name,
            "covers": int(covers or 1),
            "status": "Open",
            "channel": channel_label,
            "opened_at": now_datetime(),
            "server": get_fullname(frappe.session.user) or frappe.session.user,
            "note": (note or "").strip() or None,
            "customer": customer_id if customer_id and frappe.db.exists("Customer", customer_id) else None,
            "customer_name": (customer_name or "").strip() or None,
            "customer_phone": (customer_phone or "").strip() or None,
            "delivery_address": (delivery_dict.get("address") or "").strip() or None,
            "delivery_phone": (delivery_dict.get("phone") or "").strip() or None,
            "delivery_notes": (delivery_dict.get("notes") or "").strip() or None,
            "delivery_boy": delivery_dict.get("deliveryBoyId") or None,
            "delivery_boy_name": delivery_dict.get("deliveryBoyName") or None,
            "delivery_status": "Awaiting" if channel_label == "Delivery" else None,
            "company": comp,
            "zatgo_client_id": cid,
            "items": _parse_order_items(items),
        }
    )
    if cid:
        doc, created = insert_idempotent(doc, doctype="ZG Order", client_id=cid)
    else:
        doc.insert()
        created = True

    if table_doc:
        table_doc.current_order = doc.name
        table_doc.status = "Occupied"
        table_doc.covers = int(covers or 1)
        table_doc.save()

    frappe.db.commit()
    return ok(
        _map_order_doc(doc),
        meta={"stub": False, "created": created, "idempotent": not created, "source": "ZG Order"},
    )


def _load_order(order_id: str) -> Any:
    if not frappe.db.exists("ZG Order", order_id):
        frappe.throw(f"ZG Order {order_id} not found", frappe.DoesNotExistError)
    return frappe.get_doc("ZG Order", order_id)


def get_order(name: str) -> dict[str, Any]:
    require_login()
    frappe.has_permission("ZG Order", "read", throw=True)
    doc = _load_order(name)
    return ok(_map_order_doc(doc), meta={"stub": False, "source": "ZG Order"})


def list_orders(page: int | str = 1, page_size: int | str = 50, status: str | None = None) -> dict[str, Any]:
    from zatgo_core.api.validators import parse_pagination
    from zatgo_core.api.response import paginated

    require_login()
    frappe.has_permission("ZG Order", "read", throw=True)
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: dict[str, Any] = {}
    if status:
        filters["status"] = status.title()
    total = frappe.db.count("ZG Order", filters)
    headers = frappe.get_all(
        "ZG Order",
        filters=filters,
        fields=["name"],
        order_by="opened_at desc",
        start=start,
        page_length=size_i,
    )
    names = [h.name for h in headers]
    items_by_parent: dict[str, list[dict[str, Any]]] = {n: [] for n in names}
    if names:
        rows = frappe.get_all(
            "ZG Order Item",
            filters={"parent": ["in", names]},
            fields=["parent", "name", "item_code", "item_name", "qty", "rate", "station", "status", "extras"],
            order_by="idx asc",
        )
        for r in rows:
            items_by_parent.setdefault(r.parent, []).append(r)

    docs = [frappe.get_doc("ZG Order", n) for n in names]
    data = [_map_order_doc(d, items=items_by_parent.get(d.name, [])) for d in docs]
    payload = paginated(data, page=page_i, page_size=size_i, total=total, sort="opened_at desc")
    payload["meta"] = {**payload.get("meta", {}), "stub": False, "source": "ZG Order"}
    return payload


def add_item(
    order_id: str,
    item_code: str,
    qty: float | str = 1,
    extras: Any = None,
    rate: float | str | None = None,
    station: str | None = None,
) -> dict[str, Any]:
    require_login()
    doc = _load_order(order_id)
    frappe.has_permission("ZG Order", "write", doc=doc.name, throw=True)
    if doc.status in ("Paid", "Void"):
        frappe.throw(f"Order {doc.name} is {doc.status.lower()} and cannot be changed")
    row = _parse_order_items(
        [{"item_code": item_code, "qty": qty, "rate": rate, "station": station, "extras": extras}]
    )[0]
    doc.append("items", row)
    doc.save()
    frappe.db.commit()
    return ok(_map_order_doc(doc), meta={"stub": False, "source": "ZG Order"})


def update_item_qty(order_id: str, item_row: str, qty: float | str) -> dict[str, Any]:
    require_login()
    doc = _load_order(order_id)
    frappe.has_permission("ZG Order", "write", doc=doc.name, throw=True)
    if doc.status in ("Paid", "Void"):
        frappe.throw(f"Order {doc.name} is {doc.status.lower()} and cannot be changed")
    q = flt(qty)
    if q <= 0:
        frappe.throw("Item qty must be greater than zero")
    found = False
    for row in doc.items:
        if row.name == item_row:
            row.qty = q
            found = True
            break
    if not found:
        frappe.throw(f"Order item {item_row} not found")
    doc.save()
    frappe.db.commit()
    return ok(_map_order_doc(doc), meta={"stub": False, "source": "ZG Order"})


def set_note(order_id: str, note: str) -> dict[str, Any]:
    require_login()
    doc = _load_order(order_id)
    frappe.has_permission("ZG Order", "write", doc=doc.name, throw=True)
    doc.note = (note or "").strip() or None
    doc.save()
    frappe.db.commit()
    return ok(_map_order_doc(doc), meta={"stub": False, "source": "ZG Order"})


def send_order(order_id: str) -> dict[str, Any]:
    require_login()
    doc = _load_order(order_id)
    frappe.has_permission("ZG Order", "write", doc=doc.name, throw=True)
    if doc.status in ("Paid", "Void"):
        frappe.throw(f"Order {doc.name} is {doc.status.lower()} and cannot be sent")
    if not doc.items:
        frappe.throw("Cannot send an empty order")

    for row in doc.items:
        if row.kds_synced:
            continue
        frappe.get_doc(
            {
                "doctype": "ZG KDS Ticket",
                "title": row.item_name or row.item_code,
                "order_number": doc.order_number,
                "table_name": doc.table_name,
                "item_name": row.item_name or row.item_code,
                "qty": int(row.qty or 1),
                "station": row.station or "grill",
                "status": "Queued",
                "opened_at": now_datetime(),
                "server": doc.server,
                "note": doc.note,
                "extras": row.extras,
            }
        ).insert(ignore_permissions=True)
        row.kds_synced = 1

    if doc.status == "Open":
        doc.status = "Sent"
    doc.save()
    frappe.db.commit()
    return ok(_map_order_doc(doc), meta={"stub": False, "sent": True, "source": "ZG Order"})


def void_order(order_id: str) -> dict[str, Any]:
    require_login()
    doc = _load_order(order_id)
    frappe.has_permission("ZG Order", "write", doc=doc.name, throw=True)
    if doc.status == "Paid":
        frappe.throw(
            f"Order {doc.name} is already paid (Sales Invoice {doc.sales_invoice}). "
            "Cancel the invoice through the accounting flow instead of voiding the order."
        )
    if doc.status == "Void":
        return ok(_map_order_doc(doc), meta={"stub": False, "source": "ZG Order"})

    doc.status = "Void"
    doc.save()

    if doc.table:
        table_doc = frappe.get_doc("ZG Table", doc.table)
        if table_doc.current_order == doc.name:
            table_doc.current_order = None
            table_doc.status = "Free"
            table_doc.covers = 0
            table_doc.save()

    frappe.db.commit()
    return ok(_map_order_doc(doc), meta={"stub": False, "voided": True, "source": "ZG Order"})


def give_to_delivery(order_id: str) -> dict[str, Any]:
    require_login()
    doc = _load_order(order_id)
    frappe.has_permission("ZG Order", "write", doc=doc.name, throw=True)
    if not doc.delivery_boy:
        frappe.throw("Assign a delivery boy before handing this order to delivery")

    from zatgo_core.api.v1.delivery import stops as delivery_stops

    items_summary = ", ".join(
        f"{int(r.qty or 1)}× {r.item_name or r.item_code}" for r in doc.items
    )[:140]
    is_cod = not doc.payment_entry
    result = delivery_stops.create(
        title=f"POS {doc.order_number}",
        order_number=doc.order_number,
        invoice_number=doc.sales_invoice or doc.order_number,
        customer=doc.customer_name or "Walk-in",
        address=doc.delivery_address or "",
        phone=doc.delivery_phone or doc.customer_phone or "",
        window_label="ASAP",
        items_summary=items_summary,
        delivery_boy=doc.delivery_boy,
        status="Assigned",
        remarks=doc.delivery_notes,
        payment_method="COD" if is_cod else "Prepaid",
    )
    doc.delivery_stop = result["data"]["id"]
    doc.delivery_status = "Handed Off"
    doc.save()
    frappe.db.commit()
    return ok(_map_order_doc(doc), meta={"stub": False, "source": "ZG Order"})


# --- tables ------------------------------------------------------------


def list_tables(page: int | str = 1, page_size: int | str = 100) -> dict[str, Any]:
    from zatgo_core.api.validators import parse_pagination
    from zatgo_core.api.response import paginated

    require_login()
    frappe.has_permission("ZG Table", "read", throw=True)
    page_i, size_i, start = parse_pagination(page, page_size)
    total = frappe.db.count("ZG Table")
    rows = frappe.get_all(
        "ZG Table",
        fields=["table_code", "table_name", "zone", "seats", "status", "covers", "current_order"],
        order_by="table_name asc",
        start=start,
        page_length=size_i,
    )
    data = [_map_table_doc(r) for r in rows]
    payload = paginated(data, page=page_i, page_size=size_i, total=total, sort="table_name asc")
    payload["meta"] = {**payload.get("meta", {}), "stub": False, "source": "ZG Table"}
    return payload


def get_table(name: str) -> dict[str, Any]:
    require_login()
    frappe.has_permission("ZG Table", "read", throw=True)
    if not frappe.db.exists("ZG Table", name):
        frappe.throw(f"ZG Table {name} not found", frappe.DoesNotExistError)
    doc = frappe.get_doc("ZG Table", name)
    return ok(_map_table_doc(doc), meta={"stub": False, "source": "ZG Table"})


def seat_table(table_id: str, covers: int | str = 1, client_id: str | None = None) -> dict[str, Any]:
    return create_order(
        table=table_id,
        covers=covers,
        channel="dine_in",
        items=[],
        client_id=client_id,
    )


def set_table_status(table_id: str, status: str) -> dict[str, Any]:
    require_login()
    if not frappe.db.exists("ZG Table", table_id):
        frappe.throw(f"ZG Table {table_id} not found", frappe.DoesNotExistError)
    frappe.has_permission("ZG Table", "write", doc=table_id, throw=True)
    label = _TABLE_STATUS_MAP.get(str(status or "").lower())
    if not label:
        frappe.throw(f"Unknown table status: {status}")
    doc = frappe.get_doc("ZG Table", table_id)
    doc.status = label
    if label == "Free":
        doc.current_order = None
        doc.covers = 0
    doc.save()
    frappe.db.commit()
    return ok(_map_table_doc(doc), meta={"stub": False, "source": "ZG Table"})


def mark_billing(order_id: str) -> dict[str, Any]:
    require_login()
    doc = _load_order(order_id)
    frappe.has_permission("ZG Order", "write", doc=doc.name, throw=True)
    if doc.table:
        table_doc = frappe.get_doc("ZG Table", doc.table)
        table_doc.status = "Billing"
        table_doc.save()
    frappe.db.commit()
    return ok(_map_order_doc(doc), meta={"stub": False, "source": "ZG Order"})


# --- payment / checkout --------------------------------------------------


def payment_modes() -> dict[str, Any]:
    require_login()
    rows = frappe.get_all("Mode of Payment", filters={"enabled": 1}, fields=["name"], order_by="name asc")
    return ok([r.name for r in rows], meta={"stub": False, "source": "Mode of Payment"})


def pay(order_id: str, method: str, client_id: str) -> dict[str, Any]:
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent
    from zatgo_core.services.vansalex_service import _apply_sales_taxes

    require_login()
    cid = require_str(client_id, "client_id")
    method_key = str(method or "").lower()
    mop = _MODE_OF_PAYMENT_MAP.get(method_key)
    if not mop:
        frappe.throw(f"Unknown payment method: {method}")

    doc = _load_order(order_id)
    frappe.has_permission("ZG Order", "write", doc=doc.name, throw=True)

    if doc.status == "Paid" and doc.sales_invoice:
        si = frappe.get_doc("Sales Invoice", doc.sales_invoice)
        pe = frappe.get_doc("Payment Entry", doc.payment_entry) if doc.payment_entry else None
        return ok(
            {
                "order": _map_order_doc(doc),
                "payment": _map_payment_record(doc, si, pe, method_key),
            },
            meta={"stub": False, "idempotent": True, "source": "ZG Order"},
        )
    if doc.status == "Void":
        frappe.throw(f"Order {doc.name} is void and cannot be paid")
    if not doc.items:
        frappe.throw("Cannot check out an empty order")

    frappe.has_permission("Sales Invoice", "create", throw=True)
    comp = doc.company or _default_company()
    customer = _resolve_pos_customer(doc.customer, doc.customer_name, doc.customer_phone)
    if not doc.customer:
        doc.customer = customer

    si_created = False
    if doc.sales_invoice:
        si = frappe.get_doc("Sales Invoice", doc.sales_invoice)
    else:
        warehouse = _resolve_pos_warehouse(comp)
        si = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": customer,
                "company": comp,
                "posting_date": today(),
                "currency": frappe.get_cached_value("Company", comp, "default_currency"),
                "update_stock": 1,
                "set_warehouse": warehouse,
                "remarks": f"Resto POS order {doc.order_number}",
                "items": [
                    {
                        "item_code": row.item_code,
                        "item_name": row.item_name,
                        "qty": row.qty,
                        "rate": row.rate,
                        "warehouse": warehouse,
                    }
                    for row in doc.items
                ],
                "zatgo_client_id": cid,
            }
        )
        _apply_sales_taxes(si, comp)
        si, si_created = insert_idempotent(si, doctype="Sales Invoice", client_id=cid)
        if int(si.docstatus or 0) != 1:
            try:
                si.submit()
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                si.reload()
                frappe.log_error(title="Resto POS Sales Invoice submit failed", message=frappe.get_traceback())
                frappe.throw(
                    f"Could not submit the invoice for order {doc.order_number}. "
                    f"It was saved as a draft ({si.name}) — fix the underlying issue and retry."
                )
        doc.sales_invoice = si.name

    # COD delivery: dispatch the invoice, don't record money that hasn't
    # been collected yet — the delivery boy settles it on handoff.
    is_cod = doc.channel == "Delivery" and method_key == "cash"
    pe = None
    if not is_cod:
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

        pay_cid = f"{cid}:pay"
        existing_pe = find_by_client_id("Payment Entry", pay_cid)
        if existing_pe:
            pe = frappe.get_doc("Payment Entry", existing_pe)
        else:
            pe = get_payment_entry("Sales Invoice", si.name)
            pe.mode_of_payment = mop
            pe.zatgo_client_id = pay_cid
            pe, _pe_created = insert_idempotent(pe, doctype="Payment Entry", client_id=pay_cid)
            if int(pe.docstatus or 0) != 1:
                try:
                    pe.submit()
                    frappe.db.commit()
                except Exception:
                    frappe.db.rollback()
                    pe.reload()
                    frappe.log_error(title="Resto POS Payment Entry submit failed", message=frappe.get_traceback())
                    frappe.throw(
                        f"The invoice for order {doc.order_number} posted, but recording the "
                        f"payment failed. It was saved as a draft ({pe.name}) — retry payment."
                    )
        doc.payment_entry = pe.name

    doc.status = "Paid"
    doc.save()
    frappe.db.commit()

    return ok(
        {
            "order": _map_order_doc(doc),
            "payment": _map_payment_record(doc, si, pe, method_key),
        },
        meta={"stub": False, "created": si_created, "source": "ZG Order"},
    )


def _map_payment_record(order: Any, si: Any, pe: Any, method_key: str) -> dict[str, Any]:
    channel = (order.channel or "Counter").lower().replace(" ", "_")
    return {
        "id": pe.name if pe else si.name,
        "orderId": order.name,
        "orderNumber": order.order_number,
        "method": method_key,
        "amount": float(si.grand_total or 0),
        "paidAt": str((pe.posting_date if pe else si.posting_date) or ""),
        "channel": channel,
    }
