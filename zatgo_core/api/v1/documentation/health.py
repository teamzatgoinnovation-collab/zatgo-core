"""Documentation health endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.v1._stubs import stub_status


@frappe.whitelist()
def ping() -> dict[str, Any]:
    """Authenticated liveness for Documentation clients."""
    return stub_status("documentation", "Documentation", domain="meta")


@frappe.whitelist()
def status() -> dict[str, Any]:
    """Namespace status (stub until domain DocTypes exist)."""
    return stub_status("documentation", "Documentation", domain="meta")
