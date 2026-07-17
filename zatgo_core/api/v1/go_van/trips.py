"""Go Van trips — ZG Trip DocType."""

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
        "customer": r.get("customer"),
        "address": r.get("address"),
        "sequence": r.get("sequence"),
        "lat": r.get("lat"),
        "lng": r.get("lng"),
        "status": r.get("status"),
        "planned_at": str(r.get("planned_at") or ""),
    }


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_zg(
        "ZG Trip",
        fields=["name", "title", "customer", "address", "sequence", "lat", "lng", "status", "planned_at"],
        page=page,
        page_size=page_size,
        map_row=_map,
    )


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_zg("ZG Trip", name, map_doc=lambda d: _map(d))
