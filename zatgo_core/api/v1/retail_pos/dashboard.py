"""Retail POS dashboard counters (today's submitted Sales Invoices)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import retail_pos_service as svc


@frappe.whitelist()
def counts() -> dict[str, Any]:
    return svc.dashboard_counts()
