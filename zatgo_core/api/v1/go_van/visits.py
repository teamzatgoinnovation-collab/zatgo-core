"""Go Van visits — ZG Trip status updates with optional GPS."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.go_van_service import update_visit


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
    return update_visit(
        client_id=client_id,
        stop_id=stop_id,
        visit_status=visit_status,
        lat=lat,
        lng=lng,
        notes=notes,
        no_sale_reason=no_sale_reason,
    )
