"""Simple driver location ping + performance snapshot."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login


def _require_boy_doctype() -> None:
    if not frappe.db.exists("DocType", "ZG Delivery Boy"):
        frappe.throw("ZG Delivery Boy DocType is not installed — migrate zatgo_core")


def _boy_for_session() -> str:
    require_login()
    _require_boy_doctype()
    user = (frappe.session.user or "").strip()
    if not user or user == "Guest":
        frappe.throw("Login required", frappe.PermissionError)
    boy = frappe.db.get_value("ZG Delivery Boy", {"user": user}, "name")
    if not boy:
        frappe.throw(
            "No delivery boy linked to your login",
            frappe.DoesNotExistError,
        )
    return str(boy)


def _snapshot(boy_name: str) -> dict[str, Any]:
    doc = frappe.get_doc("ZG Delivery Boy", boy_name)
    points = int(getattr(doc, "points", 0) or 0)
    return {
        "id": doc.name,
        "full_name": doc.full_name,
        "status": doc.status,
        "points": points,
        "deliveries_done": int(getattr(doc, "deliveries_done", 0) or 0),
        "bonus": points // 50,
        "last_lat": getattr(doc, "last_lat", None),
        "last_lng": getattr(doc, "last_lng", None),
        "last_seen_at": str(getattr(doc, "last_seen_at", "") or "") or None,
    }


@frappe.whitelist()
def me() -> dict[str, Any]:
    """Performance + last location for the signed-in courier."""
    boy = _boy_for_session()
    return ok(_snapshot(boy), meta={"source": "ZG Delivery Boy"})


@frappe.whitelist()
def ping(lat: float | str, lng: float | str, speed_kmh: float | str | None = None) -> dict[str, Any]:
    """Save current GPS on the courier (simple tracking)."""
    boy = _boy_for_session()
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        frappe.throw("lat and lng are required numbers")

    values: dict[str, Any] = {
        "last_lat": lat_f,
        "last_lng": lng_f,
        "last_seen_at": now_datetime(),
    }
    meta = frappe.get_meta("ZG Delivery Boy")
    if meta.has_field("last_lat"):
        frappe.db.set_value("ZG Delivery Boy", boy, values, update_modified=False)
        frappe.db.commit()

    data = _snapshot(boy)
    data["speed_kmh"] = None
    if speed_kmh is not None and str(speed_kmh).strip() != "":
        try:
            data["speed_kmh"] = float(speed_kmh)
        except (TypeError, ValueError):
            data["speed_kmh"] = None
    return ok(data, meta={"source": "ZG Delivery Boy", "pinged": True})
