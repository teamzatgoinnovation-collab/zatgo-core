"""Client application settings APIs (Electron / Flutter / Web)."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_str
from zatgo_core.services.app_registry_service import AppRegistryService
from zatgo_core.utils.logging import log_api


@frappe.whitelist()
def get_application_registry() -> dict[str, Any]:
    """Return client application rows configured for this site."""
    log_api("get_application_registry", user=frappe.session.user)
    return ok(AppRegistryService.get_registry())


@frappe.whitelist()
def get_application_settings() -> dict[str, Any]:
    """Return the site's single Application Settings document."""
    log_api("get_application_settings", user=frappe.session.user)
    return ok(AppRegistryService.get_application_settings())


@frappe.whitelist()
def get_client_app(app_key: str) -> dict[str, Any]:
    """Return one client app config by app_key."""
    app_key = require_str(app_key, "app_key")
    log_api("get_client_app", user=frappe.session.user, app_key=app_key)
    return ok(AppRegistryService.get_client_app(app_key))


@frappe.whitelist()
def is_client_enabled(app_key: str) -> dict[str, Any]:
    """Check whether a client app may run against this site."""
    app_key = require_str(app_key, "app_key")
    log_api("is_client_enabled", user=frappe.session.user, app_key=app_key)
    return ok(
        {
            "app_key": app_key,
            "enabled": AppRegistryService.is_client_enabled(app_key),
        }
    )


@frappe.whitelist()
def seed_default_client_apps(replace: int | str | bool = 0) -> dict[str, Any]:
    """Seed default Electron/Flutter/Web clients for this site."""
    log_api("seed_default_client_apps", user=frappe.session.user, replace=replace)
    replace_flag = str(replace) in ("1", "True", "true", "yes")
    return ok(AppRegistryService.seed_default_client_apps(replace=replace_flag))


@frappe.whitelist()
def sync_application_registry() -> dict[str, Any]:
    """Deprecated name — seeds client apps (does not scan Frappe apps)."""
    log_api("sync_application_registry", user=frappe.session.user)
    return ok(AppRegistryService.seed_default_client_apps(replace=False))
