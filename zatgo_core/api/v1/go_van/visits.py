"""Go Van visits — ZG Trip status updates."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services.go_van_service import update_visit


@frappe.whitelist()
def update(
    client_id: str,
    stop_id: str,
    visit_status: str,
) -> dict[str, Any]:
    return update_visit(
        client_id=client_id,
        stop_id=stop_id,
        visit_status=visit_status,
    )
