"""Field service tickets — ZG Service Ticket DocType."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_zg, list_zg


def _map(row: Any) -> dict[str, Any]:
    r = row.as_dict() if callable(getattr(row, "as_dict", None)) else dict(row)
    return {
        "id": r.get("name"),
        "name": r.get("name"),
        "title": r.get("title"),
        "number": r.get("number"),
        "subject": r.get("title") or r.get("issue"),
        "issue": r.get("issue"),
        "customer": r.get("customer"),
        "address": r.get("address"),
        "priority": r.get("priority"),
        "status": r.get("status"),
        "scheduled_at": str(r.get("scheduled_at") or ""),
    }


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_zg(
        "ZG Service Ticket",
        fields=["name", "title", "number", "customer", "address", "issue", "priority", "status", "scheduled_at"],
        page=page,
        page_size=page_size,
        map_row=_map,
    )


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_zg("ZG Service Ticket", name, map_doc=lambda d: _map(d))
