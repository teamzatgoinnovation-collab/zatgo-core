"""Configuration center APIs — plugin registry + settings loader."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import parse_json_dict, require_str
from zatgo_core.plugins.discover import discover_and_register_manifests
from zatgo_core.services.config_loader_service import ConfigLoaderService
from zatgo_core.services.plugin_registry_service import PluginRegistryService
from zatgo_core.utils.logging import log_api


@frappe.whitelist()
def get_applications() -> dict[str, Any]:
    """List registered applications visible to the current user."""
    log_api("config.get_applications", user=frappe.session.user)
    return ok(PluginRegistryService.list_applications())


@frappe.whitelist()
def get_application(app_key: str) -> dict[str, Any]:
    """Return one application and its setting section tree."""
    app_key = require_str(app_key, "app_key")
    log_api("config.get_application", user=frappe.session.user, app_key=app_key)
    data = PluginRegistryService.get_application(app_key)
    if not data:
        frappe.throw(frappe._("Application not found"), frappe.DoesNotExistError)
    return ok(data)


@frappe.whitelist()
def register_application(manifest: Any) -> dict[str, Any]:
    """Upsert an application manifest into the plugin registry."""
    payload = parse_json_dict(manifest, "manifest")
    log_api(
        "config.register_application",
        user=frappe.session.user,
        app_key=payload.get("app_key"),
    )
    return ok(PluginRegistryService.register_application(payload))


@frappe.whitelist()
def seed_bundled_manifests() -> dict[str, Any]:
    """Re-register POS / Delivery / Kitchen bundled manifests."""
    log_api("config.seed_bundled_manifests", user=frappe.session.user)
    return ok(discover_and_register_manifests())


@frappe.whitelist()
def get_settings(app_key: str, section_key: str) -> dict[str, Any]:
    """Load settings payload for an application section."""
    app_key = require_str(app_key, "app_key")
    section_key = require_str(section_key, "section_key")
    log_api(
        "config.get_settings",
        user=frappe.session.user,
        app_key=app_key,
        section_key=section_key,
    )
    return ok(ConfigLoaderService.get_settings(app_key, section_key))


@frappe.whitelist()
def update_settings(app_key: str, section_key: str, values: Any) -> dict[str, Any]:
    """Persist settings for a section."""
    app_key = require_str(app_key, "app_key")
    section_key = require_str(section_key, "section_key")
    payload = parse_json_dict(values, "values")
    log_api(
        "config.update_settings",
        user=frappe.session.user,
        app_key=app_key,
        section_key=section_key,
    )
    return ok(ConfigLoaderService.update_settings(app_key, section_key, payload))


@frappe.whitelist()
def reset_settings(app_key: str, section_key: str) -> dict[str, Any]:
    """Reset a section to its manifest defaults."""
    app_key = require_str(app_key, "app_key")
    section_key = require_str(section_key, "section_key")
    log_api(
        "config.reset_settings",
        user=frappe.session.user,
        app_key=app_key,
        section_key=section_key,
    )
    return ok(ConfigLoaderService.reset_settings(app_key, section_key))


@frappe.whitelist()
def export_settings(profile_name: str | None = None) -> dict[str, Any]:
    """Export visible application settings (optionally save as Config Profile)."""
    log_api("config.export_settings", user=frappe.session.user, profile=profile_name)
    return ok(ConfigLoaderService.export_settings(profile_name))


@frappe.whitelist()
def import_settings(payload: Any) -> dict[str, Any]:
    """Import settings JSON previously exported from Core."""
    data = parse_json_dict(payload, "payload")
    log_api("config.import_settings", user=frappe.session.user)
    return ok(ConfigLoaderService.import_settings(data))


@frappe.whitelist()
def validate_configuration(app_key: str) -> dict[str, Any]:
    """Validate an application's section wiring."""
    app_key = require_str(app_key, "app_key")
    log_api("config.validate_configuration", user=frappe.session.user, app_key=app_key)
    return ok(ConfigLoaderService.validate_configuration(app_key))


@frappe.whitelist()
def search_settings(query: str) -> dict[str, Any]:
    """Search setting sections across applications."""
    log_api("config.search_settings", user=frappe.session.user, query=query)
    return ok(PluginRegistryService.search_settings(query))


@frappe.whitelist()
def get_dashboard() -> dict[str, Any]:
    """Dashboard metrics for the configuration center."""
    log_api("config.get_dashboard", user=frappe.session.user)
    return ok(ConfigLoaderService.get_dashboard())
