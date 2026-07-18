"""Hub health/catalog plus system health for ZatGo Core."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.api.v1.catalog_data import PRODUCT_CATALOG
from zatgo_core.services.health_service import HealthService
from zatgo_core.utils.logging import log_api


@frappe.whitelist(allow_guest=True)
def ping() -> dict[str, Any]:
    """Lightweight liveness check (guest allowed for site smoke tests)."""
    return ok({"app": "zatgo_core", "version": "0.1.0", "ok": True})


@frappe.whitelist()
def catalog() -> dict[str, Any]:
    """List product API namespaces under zatgo_core.api.v1 (login required)."""
    require_login()
    return ok(
        {"products": PRODUCT_CATALOG},
        meta={"count": len(PRODUCT_CATALOG)},
    )


@frappe.whitelist()
def status() -> dict[str, Any]:
    """Hub status including whether sibling apps are installed."""
    require_login()
    installed = set(frappe.get_installed_apps())
    products = []
    for entry in PRODUCT_CATALOG:
        row = dict(entry)
        row["installed"] = "zatgo_core" in installed
        products.append(row)
    return ok(
        {
            "app": "zatgo_core",
            "installed_apps": sorted(installed),
            "products": products,
        }
    )


@frappe.whitelist()
def get_system_health() -> dict[str, Any]:
    """Return system health snapshot for Core Administration dashboards."""
    log_api("get_system_health", user=frappe.session.user)
    return ok(HealthService.get_system_health())
