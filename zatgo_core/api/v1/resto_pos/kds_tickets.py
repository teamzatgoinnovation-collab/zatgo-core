"""Kitchen Display System tickets — ZG KDS Ticket DocType."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.erpnext_reads import get_zg, list_zg

_STATUS_FLOW = ("Queued", "Preparing", "Ready", "Served")
_STATIONS = ("grill", "cold", "bar", "dessert", "counter")


def _row_dict(row: Any) -> dict[str, Any]:
    if callable(getattr(row, "as_dict", None)):
        return row.as_dict()
    return dict(row)


def _map(row: Any) -> dict[str, Any]:
    r = _row_dict(row)
    status = (r.get("status") or "Queued").lower()
    extras_raw = (r.get("extras") or "").strip()
    extras = [{"id": e, "name": e, "price": 0} for e in extras_raw.split(",") if e.strip()] if extras_raw else []
    return {
        "id": r.get("name"),
        "name": r.get("name"),
        "orderId": r.get("order_number") or r.get("name"),
        "order_number": r.get("order_number"),
        "orderNumber": r.get("order_number"),
        "tableName": r.get("table_name") or "",
        "table_name": r.get("table_name") or "",
        "title": r.get("title") or r.get("item_name"),
        "item_name": r.get("item_name"),
        "itemName": r.get("item_name"),
        "qty": int(r.get("qty") or 1),
        "station": (r.get("station") or "grill").lower(),
        "status": status,
        "openedAt": str(r.get("opened_at") or ""),
        "opened_at": str(r.get("opened_at") or ""),
        "server": r.get("server") or "",
        "note": r.get("note") or "",
        "extras": extras,
    }


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 50,
    station: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """List open kitchen tickets (excludes Served by default when status omitted)."""
    filters: dict[str, Any] = {}
    if station:
        filters["station"] = station.lower()
    if status:
        filters["status"] = status.title() if status.lower() != "queued" else "Queued"
        if status.lower() == "preparing":
            filters["status"] = "Preparing"
        elif status.lower() == "ready":
            filters["status"] = "Ready"
        elif status.lower() == "served":
            filters["status"] = "Served"
        elif status.lower() == "queued":
            filters["status"] = "Queued"
    return list_zg(
        "ZG KDS Ticket",
        fields=[
            "name",
            "title",
            "order_number",
            "table_name",
            "item_name",
            "qty",
            "station",
            "status",
            "opened_at",
            "server",
            "note",
            "extras",
        ],
        page=page,
        page_size=page_size,
        filters=filters or None,
        map_row=_map,
        order_by="opened_at asc",
    )


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_zg("ZG KDS Ticket", name, map_doc=lambda d: _map(d))


@frappe.whitelist()
def advance(name: str) -> dict[str, Any]:
    """Advance ticket: Queued → Preparing → Ready → Served."""
    require_login()
    if not frappe.db.exists("ZG KDS Ticket", name):
        frappe.throw(f"ZG KDS Ticket {name} not found", frappe.DoesNotExistError)
    frappe.has_permission("ZG KDS Ticket", "write", doc=name, throw=True)
    doc = frappe.get_doc("ZG KDS Ticket", name)
    cur = doc.status or "Queued"
    try:
        idx = _STATUS_FLOW.index(cur)
    except ValueError:
        idx = 0
    if idx >= len(_STATUS_FLOW) - 1:
        return ok(_map(doc), meta={"stub": False, "message": "Already served"})
    doc.status = _STATUS_FLOW[idx + 1]
    doc.save()
    frappe.db.commit()
    return ok(_map(doc), meta={"stub": False, "advanced": True})


@frappe.whitelist()
def recall(name: str) -> dict[str, Any]:
    """Recall one step back (not below Queued)."""
    require_login()
    if not frappe.db.exists("ZG KDS Ticket", name):
        frappe.throw(f"ZG KDS Ticket {name} not found", frappe.DoesNotExistError)
    frappe.has_permission("ZG KDS Ticket", "write", doc=name, throw=True)
    doc = frappe.get_doc("ZG KDS Ticket", name)
    cur = doc.status or "Queued"
    try:
        idx = _STATUS_FLOW.index(cur)
    except ValueError:
        idx = 0
    if idx <= 0:
        return ok(_map(doc), meta={"stub": False, "message": "Already queued"})
    doc.status = _STATUS_FLOW[idx - 1]
    doc.save()
    frappe.db.commit()
    return ok(_map(doc), meta={"stub": False, "recalled": True})


@frappe.whitelist()
def bump_station(station: str) -> dict[str, Any]:
    """Mark all Ready tickets at a station as Served."""
    require_login()
    station = (station or "").lower().strip()
    if station not in _STATIONS:
        frappe.throw(f"Unknown station: {station}")
    names = frappe.get_all(
        "ZG KDS Ticket",
        filters={"station": station, "status": "Ready"},
        pluck="name",
    )
    for n in names:
        frappe.db.set_value("ZG KDS Ticket", n, "status", "Served")
    frappe.db.commit()
    return ok(
        {"station": station, "count": len(names)},
        meta={"stub": False, "bumped": True},
    )
