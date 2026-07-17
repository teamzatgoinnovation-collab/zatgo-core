"""Fleet vehicles — ZG Vehicle DocType."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.erpnext_reads import get_zg, list_zg


def _map(row: Any) -> dict[str, Any]:
    r = row.as_dict() if callable(getattr(row, "as_dict", None)) else dict(row)
    return {
        "id": r.get("name"),
        "name": r.get("title") or r.get("plate") or r.get("name"),
        "title": r.get("title"),
        "plate": r.get("plate"),
        "vehicle_type": r.get("vehicle_type"),
        "status": r.get("status"),
        "driver_name": r.get("driver_name"),
    }


@frappe.whitelist()
def list(page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    return list_zg(
        "ZG Vehicle",
        fields=["name", "title", "plate", "vehicle_type", "status", "driver_name"],
        page=page,
        page_size=page_size,
        map_row=_map,
    )


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_zg("ZG Vehicle", name, map_doc=lambda d: _map(d))
