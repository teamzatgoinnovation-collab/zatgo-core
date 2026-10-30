"""Resto POS dashboard counters."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import resto_pos_admin_service as svc


@frappe.whitelist()
def counts() -> dict[str, Any]:
    return svc.dashboard_counts()
