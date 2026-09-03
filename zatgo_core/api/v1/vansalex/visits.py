"""VanSaleX visits — ZG Trip status updates with optional GPS."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.validators import require_login
from zatgo_core.services.vansalex_service import update_visit


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
    # Row-level ownership is enforced inside update_visit via
    # assert_trip_access — an earlier version tried to check it here by
    # resolving stop_id as a ZG Delivery Stop and walking to its parent,
    # which never matched a real caller, so the check silently never ran.
    return update_visit(
        client_id=client_id,
        stop_id=stop_id,
        visit_status=visit_status,
        lat=lat,
        lng=lng,
        notes=notes,
        no_sale_reason=no_sale_reason,
    )
