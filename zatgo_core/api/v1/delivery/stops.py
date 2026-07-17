"""Delivery stops — ZG Delivery Stop DocType."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, now_datetime

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.erpnext_reads import get_zg, list_zg

_VALID_STATUS = {
    "Assigned",
    "Accepted",
    "Rejected",
    "Reached Restaurant",
    "Picked Up",
    "Out For Delivery",
    "Delivered",
    "Failed",
    "Cancelled",
    "Returned",
}

_ACTIVE_STATUS = {
    "Assigned",
    "Accepted",
    "Reached Restaurant",
    "Picked Up",
    "Out For Delivery",
}

_TERMINAL_STATUS = {
    "Delivered",
    "Failed",
    "Rejected",
    "Cancelled",
    "Returned",
}

# Driver workflow transitions (2A).
_TRANSITIONS: dict[str, set[str]] = {
    "Assigned": {"Accepted", "Rejected", "Cancelled"},
    "Accepted": {
        "Reached Restaurant",
        "Picked Up",
        "Out For Delivery",
        "Failed",
        "Cancelled",
    },
    "Reached Restaurant": {"Picked Up", "Failed", "Cancelled"},
    "Picked Up": {"Out For Delivery", "Failed", "Cancelled", "Returned"},
    "Out For Delivery": {"Delivered", "Failed", "Cancelled", "Returned"},
    "Delivered": set(),
    "Failed": set(),
    "Rejected": set(),
    "Cancelled": set(),
    "Returned": set(),
}

# Legacy → new (one-time migration + normalize).
_LEGACY_STATUS = {
    "Pending": "Assigned",
    "En Route": "Out For Delivery",
    "Arrived": "Out For Delivery",
}

_VALID_POD_METHOD = {"OTP", "Signature", "Photo"}

_LIST_FIELDS = [
    "name",
    "title",
    "order_number",
    "invoice_number",
    "customer",
    "address",
    "city",
    "area",
    "window_label",
    "items_summary",
    "sequence",
    "phone",
    "status",
    "priority",
    "delivery_boy",
    "assigned_at",
    "expected_at",
    "remarks",
    "payment_method",
    "cod_amount",
    "paid_amount",
    "balance",
    "delivery_charges",
    "lat",
    "lng",
    "pod_method",
    "pod_signed_by",
    "pod_otp",
    "pod_note",
    "pod_captured_at",
    "pod_photo",
    "pod_signature_file",
]

POINTS_PER_DELIVERY = 10


def _map(row: Any) -> dict[str, Any]:
    r = row.as_dict() if callable(getattr(row, "as_dict", None)) else dict(row)
    status = r.get("status")
    if status in _LEGACY_STATUS:
        status = _LEGACY_STATUS[status]
    return {
        "id": r.get("name"),
        "name": r.get("name"),
        "title": r.get("title"),
        "order": r.get("order_number"),
        "order_number": r.get("order_number"),
        "invoice_number": r.get("invoice_number"),
        "customer": r.get("customer"),
        "address": r.get("address"),
        "city": r.get("city"),
        "area": r.get("area"),
        "window": r.get("window_label"),
        "items": r.get("items_summary"),
        "sequence": r.get("sequence"),
        "phone": r.get("phone"),
        "status": status,
        "priority": r.get("priority") or "Normal",
        "delivery_boy": r.get("delivery_boy"),
        "assigned_at": str(r.get("assigned_at") or "") or None,
        "expected_at": str(r.get("expected_at") or "") or None,
        "remarks": r.get("remarks"),
        "payment_method": r.get("payment_method"),
        "cod_amount": flt(r.get("cod_amount")),
        "paid_amount": flt(r.get("paid_amount")),
        "balance": flt(r.get("balance")),
        "delivery_charges": flt(r.get("delivery_charges")),
        "lat": r.get("lat"),
        "lng": r.get("lng"),
        "pod_method": r.get("pod_method"),
        "pod_signed_by": r.get("pod_signed_by"),
        "pod_otp": r.get("pod_otp"),
        "pod_note": r.get("pod_note"),
        "pod_captured_at": str(r.get("pod_captured_at") or "") or None,
        "pod_photo": r.get("pod_photo"),
        "pod_signature_file": r.get("pod_signature_file"),
    }


def _require_stop_doctype() -> None:
    if not frappe.db.exists("DocType", "ZG Delivery Stop"):
        frappe.throw("ZG Delivery Stop DocType is not installed — migrate zatgo_core")


def _resolve_boy(delivery_boy: str | None) -> str | None:
    boy = (delivery_boy or "").strip()
    if not boy:
        return None
    if not frappe.db.exists("DocType", "ZG Delivery Boy"):
        frappe.throw("ZG Delivery Boy DocType is not installed — migrate zatgo_core")
    if not frappe.db.exists("ZG Delivery Boy", boy):
        by_code = frappe.db.exists("ZG Delivery Boy", {"code": boy})
        if by_code:
            return str(by_code)
        frappe.throw(f"Delivery boy {boy} not found", frappe.DoesNotExistError)
    return boy


def _set_boy_on_route(boy: str | None) -> None:
    if not boy or not frappe.db.exists("DocType", "ZG Delivery Boy"):
        return
    current = frappe.db.get_value("ZG Delivery Boy", boy, "status")
    if current == "Available":
        frappe.db.set_value("ZG Delivery Boy", boy, "status", "On Route")


def _maybe_free_boy(boy: str | None) -> None:
    if not boy or not frappe.db.exists("DocType", "ZG Delivery Boy"):
        return
    active = frappe.db.count(
        "ZG Delivery Stop",
        {"delivery_boy": boy, "status": ("in", list(_ACTIVE_STATUS))},
    )
    if active == 0:
        frappe.db.set_value("ZG Delivery Boy", boy, "status", "Available")


def _normalize_status(status: str | None) -> str:
    raw = (status or "").strip()
    if not raw:
        frappe.throw("status is required")
    if raw in _LEGACY_STATUS:
        raw = _LEGACY_STATUS[raw]
    aliases = {
        "pending": "Assigned",
        "assigned": "Assigned",
        "accepted": "Accepted",
        "rejected": "Rejected",
        "reachedrestaurant": "Reached Restaurant",
        "reached": "Reached Restaurant",
        "pickedup": "Picked Up",
        "pickup": "Picked Up",
        "outfordelivery": "Out For Delivery",
        "enroute": "Out For Delivery",
        "arrived": "Out For Delivery",
        "delivered": "Delivered",
        "failed": "Failed",
        "cancelled": "Cancelled",
        "canceled": "Cancelled",
        "returned": "Returned",
    }
    key = raw.lower().replace(" ", "").replace("_", "").replace("-", "")
    mapped = aliases.get(key) or raw
    if mapped not in _VALID_STATUS:
        frappe.throw(f"Invalid status: {status}")
    return mapped


def _assert_transition(current: str, nxt: str) -> None:
    if current == nxt:
        return
    # Treat legacy current as mapped
    if current in _LEGACY_STATUS:
        current = _LEGACY_STATUS[current]
    allowed = _TRANSITIONS.get(current, set())
    if nxt not in allowed:
        frappe.throw(f"Cannot move stop from {current} to {nxt}")


def _award_delivery_points(boy: str | None) -> None:
    if not boy or not frappe.db.exists("DocType", "ZG Delivery Boy"):
        return
    if not frappe.db.exists("ZG Delivery Boy", boy):
        return
    meta = frappe.get_meta("ZG Delivery Boy")
    if not meta.has_field("points"):
        return
    points = int(frappe.db.get_value("ZG Delivery Boy", boy, "points") or 0)
    done = int(frappe.db.get_value("ZG Delivery Boy", boy, "deliveries_done") or 0)
    frappe.db.set_value(
        "ZG Delivery Boy",
        boy,
        {"points": points + POINTS_PER_DELIVERY, "deliveries_done": done + 1},
        update_modified=False,
    )


def _float(v: Any) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _apply_status(
    name: str,
    *,
    status: str | None = None,
    pod_method: str | None = None,
    pod_signed_by: str | None = None,
    pod_otp: str | None = None,
    pod_note: str | None = None,
    pod_photo: str | None = None,
    paid_amount: float | str | None = None,
    payment_method: str | None = None,
) -> dict[str, Any]:
    require_login()
    _require_stop_doctype()
    if not frappe.db.exists("ZG Delivery Stop", name):
        frappe.throw(f"ZG Delivery Stop {name} not found", frappe.DoesNotExistError)

    frappe.has_permission("ZG Delivery Stop", "write", doc=name, throw=True)

    doc = frappe.get_doc("ZG Delivery Stop", name)
    current = (doc.status or "Assigned").strip()
    if current in _LEGACY_STATUS:
        current = _LEGACY_STATUS[current]
    if current not in _VALID_STATUS:
        current = "Assigned"

    nxt = _normalize_status(status) if status is not None else current
    _assert_transition(current, nxt)

    method = (pod_method or "").strip()
    if method:
        method_aliases = {"otp": "OTP", "signature": "Signature", "photo": "Photo"}
        method = method_aliases.get(method.lower(), method)
        if method not in _VALID_POD_METHOD:
            frappe.throw(f"Invalid pod_method: {pod_method}")

    if nxt == "Delivered" and current != "Delivered":
        # Simple complete — no signature/photo required
        if not (method or doc.pod_method):
            method = "Signature"
            doc.pod_method = method
        if not doc.pod_note:
            doc.pod_note = (pod_note or "").strip() or "Delivered"

    doc.status = nxt
    if method:
        doc.pod_method = method
    if pod_signed_by is not None:
        doc.pod_signed_by = (pod_signed_by or "").strip() or None
    if pod_otp is not None:
        doc.pod_otp = (pod_otp or "").strip() or None
    if pod_note is not None:
        doc.pod_note = (pod_note or "").strip() or None
    if pod_photo is not None and hasattr(doc, "pod_photo"):
        doc.pod_photo = (pod_photo or "").strip() or None
    if payment_method is not None and hasattr(doc, "payment_method"):
        doc.payment_method = (payment_method or "").strip() or None
    if paid_amount is not None and hasattr(doc, "paid_amount"):
        paid = _float(paid_amount)
        if paid is not None:
            doc.paid_amount = paid
            cod = flt(getattr(doc, "cod_amount", 0) or 0)
            doc.balance = max(cod - paid, 0)
    if nxt == "Delivered" and not doc.pod_captured_at:
        doc.pod_captured_at = now_datetime()
    if nxt == "Assigned" and hasattr(doc, "assigned_at") and not doc.assigned_at:
        doc.assigned_at = now_datetime()

    doc.save()

    boy = doc.delivery_boy
    if nxt in _ACTIVE_STATUS:
        _set_boy_on_route(boy)
    elif nxt in _TERMINAL_STATUS:
        if nxt == "Delivered" and current != "Delivered":
            _award_delivery_points(boy)
        _maybe_free_boy(boy)

    frappe.db.commit()
    return ok(
        _map(doc),
        meta={"stub": False, "updated": True, "source": "ZG Delivery Stop"},
    )


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
    delivery_boy: str | None = None,
    status: str | None = None,
    area: str | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    boy = (delivery_boy or "").strip()
    if boy:
        filters["delivery_boy"] = boy
    st = (status or "").strip()
    if st:
        filters["status"] = _normalize_status(st)
    if (area or "").strip():
        filters["area"] = area.strip()
    if (priority or "").strip():
        filters["priority"] = priority.strip()

    meta = frappe.get_meta("ZG Delivery Stop") if frappe.db.exists("DocType", "ZG Delivery Stop") else None
    fields = [f for f in _LIST_FIELDS if not meta or meta.has_field(f) or f == "name"]

    return list_zg(
        "ZG Delivery Stop",
        fields=fields,
        page=page,
        page_size=page_size,
        filters=filters or None,
        map_row=_map,
    )


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_zg("ZG Delivery Stop", name, map_doc=lambda d: _map(d))


@frappe.whitelist()
def create(
    title: str | None = None,
    order_number: str | None = None,
    invoice_number: str | None = None,
    customer: str | None = None,
    address: str | None = None,
    city: str | None = None,
    area: str | None = None,
    window_label: str | None = None,
    items_summary: str | None = None,
    phone: str | None = None,
    delivery_boy: str | None = None,
    status: str | None = None,
    sequence: int | str | None = None,
    lat: float | str | None = None,
    lng: float | str | None = None,
    remarks: str | None = None,
    priority: str | None = None,
    payment_method: str | None = None,
    cod_amount: float | str | None = None,
    paid_amount: float | str | None = None,
    delivery_charges: float | str | None = None,
    expected_at: str | None = None,
) -> dict[str, Any]:
    """Create a delivery stop (POS invoice handoff). Default status: Assigned."""
    require_login()
    frappe.has_permission("ZG Delivery Stop", "create", throw=True)
    _require_stop_doctype()

    order_no = (order_number or "").strip()
    cust = (customer or "").strip() or "Walk-in"
    addr = (address or "").strip()
    stop_title = (title or "").strip() or (f"POS {order_no}" if order_no else f"Delivery · {cust}")

    if not addr:
        frappe.throw("Delivery address is required")

    boy = _resolve_boy(delivery_boy)
    raw_status = (status or "Assigned").strip()
    if raw_status in _LEGACY_STATUS:
        raw_status = _LEGACY_STATUS[raw_status]
    if raw_status == "Pending":
        raw_status = "Assigned"
    stop_status = _normalize_status(raw_status)

    try:
        seq = int(sequence) if sequence is not None and str(sequence).strip() != "" else None
    except (TypeError, ValueError):
        seq = None
    if seq is None:
        seq = (frappe.db.count("ZG Delivery Stop", {"delivery_boy": boy} if boy else {}) or 0) + 1

    cod = _float(cod_amount) or 0
    paid = _float(paid_amount) or 0
    charges = _float(delivery_charges) or 0

    payload: dict[str, Any] = {
        "doctype": "ZG Delivery Stop",
        "title": stop_title,
        "order_number": order_no or None,
        "customer": cust,
        "address": addr,
        "city": (city or "").strip() or None,
        "window_label": (window_label or "").strip() or "ASAP",
        "items_summary": (items_summary or "").strip() or None,
        "phone": (phone or "").strip() or None,
        "status": stop_status,
        "delivery_boy": boy,
        "sequence": seq,
        "lat": _float(lat),
        "lng": _float(lng),
    }

    meta = frappe.get_meta("ZG Delivery Stop")
    optional = {
        "invoice_number": (invoice_number or order_no or "").strip() or None,
        "area": (area or "").strip() or None,
        "remarks": (remarks or "").strip() or None,
        "priority": (priority or "").strip() or "Normal",
        "payment_method": (payment_method or "").strip() or None,
        "cod_amount": cod,
        "paid_amount": paid,
        "balance": max(cod - paid, 0),
        "delivery_charges": charges,
        "assigned_at": now_datetime() if stop_status == "Assigned" else None,
        "expected_at": (expected_at or "").strip() or None,
    }
    for key, val in optional.items():
        if meta.has_field(key):
            payload[key] = val

    doc = frappe.get_doc(payload)
    doc.insert()

    if boy and stop_status in _ACTIVE_STATUS:
        _set_boy_on_route(boy)

    frappe.db.commit()
    return ok(_map(doc), meta={"stub": False, "created": True, "source": "ZG Delivery Stop"})


@frappe.whitelist()
def assign(name: str, delivery_boy: str) -> dict[str, Any]:
    """Assign (or reassign) a delivery boy on an existing stop."""
    require_login()
    _require_stop_doctype()
    if not frappe.db.exists("ZG Delivery Stop", name):
        frappe.throw(f"ZG Delivery Stop {name} not found", frappe.DoesNotExistError)

    frappe.has_permission("ZG Delivery Stop", "write", doc=name, throw=True)

    boy = _resolve_boy(delivery_boy)
    if not boy:
        frappe.throw("delivery_boy is required")

    doc = frappe.get_doc("ZG Delivery Stop", name)
    doc.delivery_boy = boy
    current = (doc.status or "Assigned").strip()
    if current in ("Pending", "Assigned") or current in _LEGACY_STATUS:
        doc.status = "Assigned"
        if hasattr(doc, "assigned_at") and not doc.assigned_at:
            doc.assigned_at = now_datetime()
    doc.save()

    _set_boy_on_route(boy)

    frappe.db.commit()
    return ok(_map(doc), meta={"stub": False, "assigned": True, "source": "ZG Delivery Stop"})


@frappe.whitelist()
def update(
    name: str,
    status: str | None = None,
    pod_method: str | None = None,
    pod_signed_by: str | None = None,
    pod_otp: str | None = None,
    pod_note: str | None = None,
    pod_photo: str | None = None,
    paid_amount: float | str | None = None,
    payment_method: str | None = None,
) -> dict[str, Any]:
    """Driver status / POD / payment update."""
    return _apply_status(
        name,
        status=status,
        pod_method=pod_method,
        pod_signed_by=pod_signed_by,
        pod_otp=pod_otp,
        pod_note=pod_note,
        pod_photo=pod_photo,
        paid_amount=paid_amount,
        payment_method=payment_method,
    )


@frappe.whitelist()
def accept(name: str) -> dict[str, Any]:
    return _apply_status(name, status="Accepted")


@frappe.whitelist()
def reject(name: str, pod_note: str | None = None) -> dict[str, Any]:
    return _apply_status(name, status="Rejected", pod_note=pod_note)


@frappe.whitelist()
def reach_restaurant(name: str) -> dict[str, Any]:
    return _apply_status(name, status="Reached Restaurant")


@frappe.whitelist()
def pickup(name: str) -> dict[str, Any]:
    return _apply_status(name, status="Picked Up")


@frappe.whitelist()
def start_delivery(name: str) -> dict[str, Any]:
    return _apply_status(name, status="Out For Delivery")


@frappe.whitelist()
def complete_delivery(
    name: str,
    pod_method: str | None = None,
    pod_signed_by: str | None = None,
    pod_otp: str | None = None,
    pod_note: str | None = None,
    pod_photo: str | None = None,
    paid_amount: float | str | None = None,
    status: str | None = None,  # ignored; kept for older clients that send it
) -> dict[str, Any]:
    return _apply_status(
        name,
        status="Delivered",
        pod_method=pod_method or "Signature",
        pod_signed_by=pod_signed_by,
        pod_otp=pod_otp,
        pod_note=pod_note,
        pod_photo=pod_photo,
        paid_amount=paid_amount,
    )


@frappe.whitelist()
def fail_delivery(name: str, pod_note: str | None = None) -> dict[str, Any]:
    return _apply_status(name, status="Failed", pod_note=pod_note)
