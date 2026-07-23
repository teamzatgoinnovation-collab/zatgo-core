"""Go Van visits — ZG Trip status updates with optional GPS."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.validators import require_login
from zatgo_core.services.go_van_service import update_visit
from zatgo_core.services.van_sale_access import is_vansale_admin


@frappe.whitelist()
def update(
    client_id: str,
    stop_id: str,
    visit_status: str,
    lat: float | str | None = None,
    lng: float | str | None = None,
    notes: str | None = None,
    no_sale_reason: str | None = None,
) -> dict[str, Any]:
    require_login()
    if not is_vansale_admin():
        if frappe.db.exists("ZG Delivery Stop", stop_id):
            parent_trip = frappe.db.get_value("ZG Delivery Stop", stop_id, "parent")
            if parent_trip and frappe.db.exists("ZG Trip", parent_trip):
                trip_user = frappe.db.get_value("ZG Trip", parent_trip, "sales_user") or frappe.db.get_value("ZG Trip", parent_trip, "owner")
                if trip_user and trip_user != frappe.session.user:
                    frappe.throw("Access denied: You can only update visits for your assigned trip.", frappe.PermissionError)
    return update_visit(
        client_id=client_id,
        stop_id=stop_id,
        visit_status=visit_status,
        lat=lat,
        lng=lng,
        notes=notes,
        no_sale_reason=no_sale_reason,
    )
