"""Go Van trips — ZG Trip DocType."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate

from zatgo_core.services.erpnext_reads import get_zg, list_zg
from zatgo_core.services.van_sale_access import get_profile, is_vansale_admin


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
        "sales_user": r.get("sales_user"),
        "warehouse": r.get("warehouse"),
        "vehicle": r.get("vehicle"),
        "route_title": r.get("route_title") or "",
    }


def _scope_filters(
    *,
    sales_user: str | None = None,
    warehouse: str | None = None,
    vehicle: str | None = None,
    route_title: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    admin = is_vansale_admin()

    if admin:
        if sales_user:
            filters["sales_user"] = sales_user
        if warehouse:
            filters["warehouse"] = warehouse
        if vehicle:
            filters["vehicle"] = vehicle
        if route_title:
            filters["route_title"] = route_title
    else:
        # Field user: force own assignment
        uid = frappe.session.user
        profile = get_profile(uid)
        filters["sales_user"] = uid
        if profile and profile.get("warehouse"):
            # Prefer sales_user; warehouse is additional when set on trips
            pass
        if warehouse and profile and warehouse == profile.get("warehouse"):
            filters["warehouse"] = warehouse
        if vehicle and profile and vehicle == profile.get("vehicle"):
            filters["vehicle"] = vehicle
        if route_title and profile and route_title == profile.get("route_title"):
            filters["route_title"] = route_title

    if date and frappe.db.has_column("ZG Trip", "planned_at"):
        day = getdate(date)
        filters["planned_at"] = ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]

    return filters


@frappe.whitelist()
def list(
    page: int | str = 1,
    page_size: int | str = 20,
    sales_user: str | None = None,
    warehouse: str | None = None,
    vehicle: str | None = None,
    route_title: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    fields = [
        "name",
        "title",
        "customer",
        "address",
        "sequence",
        "lat",
        "lng",
        "status",
        "planned_at",
    ]
    for col in ("sales_user", "warehouse", "vehicle", "route_title"):
        if frappe.db.has_column("ZG Trip", col):
            fields.append(col)

    filters = _scope_filters(
        sales_user=sales_user,
        warehouse=warehouse,
        vehicle=vehicle,
        route_title=route_title,
        date=date,
    )
    # Drop filters for columns that do not exist yet (pre-migrate).
    filters = {
        k: v
        for k, v in filters.items()
        if k == "planned_at" or frappe.db.has_column("ZG Trip", k)
    }

    return list_zg(
        "ZG Trip",
        fields=fields,
        page=page,
        page_size=page_size,
        filters=filters or None,
        order_by="sequence asc, planned_at asc",
        map_row=_map,
    )


@frappe.whitelist()
def get(name: str) -> dict[str, Any]:
    return get_zg("ZG Trip", name, map_doc=lambda d: _map(d))
