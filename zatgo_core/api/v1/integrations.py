"""Integration and printer APIs."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.services.settings_service import SettingsService
from zatgo_core.utils.logging import log_api


@frappe.whitelist()
def get_integrations() -> dict[str, Any]:
    """Return integration settings (secrets are Password fields)."""
    log_api("get_integrations", user=frappe.session.user)
    return ok(SettingsService.get_integrations())


@frappe.whitelist()
def get_printers() -> dict[str, Any]:
    """Return printer settings."""
    log_api("get_printers", user=frappe.session.user)
    return ok(SettingsService.get_printers())
