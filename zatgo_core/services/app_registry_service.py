"""Site-scoped client application settings (Electron / Flutter / Web).

This is NOT the Frappe/ERPNext custom-app list. Each ERPNext site has one
ZG Application Settings document that enables and configures product clients.
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.cache.manager import cache_manager
from zatgo_core.constants.client_apps import DEFAULT_CLIENT_APPS
from zatgo_core.constants.settings import CACHE_KEYS, DOCTYPES
from zatgo_core.permissions.guards import assert_can_read_settings, assert_can_write_settings
from zatgo_core.repositories.settings_repository import SettingsRepository
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

APPLICATION_SETTINGS = "ZG Application Settings"


class AppRegistryService:
    """Read/write site Application Settings for client products."""

    @classmethod
    def get_application_settings(cls) -> dict[str, Any]:
        assert_can_read_settings("apps")

        def _load() -> dict[str, Any]:
            doc = SettingsRepository.get_single(APPLICATION_SETTINGS)
            return doc.as_dict()

        return cache_manager.get_or_set(CACHE_KEYS["APP_REGISTRY"], _load)

    @classmethod
    def get_registry(cls) -> list[dict[str, Any]]:
        """Return client application rows for this site."""
        settings = cls.get_application_settings()
        return list(settings.get("client_apps") or [])

    @classmethod
    def get_client_app(cls, app_key: str) -> dict[str, Any] | None:
        for row in cls.get_registry():
            if row.get("app_key") == app_key:
                return row
        return None

    @classmethod
    def is_client_enabled(cls, app_key: str) -> bool:
        settings = cls.get_application_settings()
        row = cls.get_client_app(app_key)
        if row:
            return bool(row.get("enabled")) and not bool(row.get("maintenance_mode"))
        return bool(settings.get("allow_unknown_clients"))

    @classmethod
    def seed_default_client_apps(cls, *, replace: bool = False) -> dict[str, Any]:
        """Seed default Electron/Flutter/Web clients for this site."""
        assert_can_write_settings("apps")
        if not frappe.db.exists("DocType", APPLICATION_SETTINGS):
            frappe.throw(frappe._("ZG Application Settings DocType is not available"))

        doc = SettingsRepository.get_single(APPLICATION_SETTINGS)
        existing_keys = {row.app_key for row in (doc.client_apps or [])}

        if replace:
            doc.set("client_apps", [])
            existing_keys = set()

        seeded = 0
        for spec in DEFAULT_CLIENT_APPS:
            key = str(spec["app_key"])
            if key in existing_keys:
                continue
            doc.append("client_apps", dict(spec))
            existing_keys.add(key)
            seeded += 1

        if not doc.default_client_app and doc.client_apps:
            enabled = next((r.app_key for r in doc.client_apps if r.enabled), None)
            doc.default_client_app = enabled or doc.client_apps[0].app_key

        if not doc.site_label:
            doc.site_label = "ZatGo"

        doc.flags.ignore_zg_audit = True
        doc.save(ignore_permissions=True)
        cache_manager.delete(CACHE_KEYS["APP_REGISTRY"])
        logger.info("Seeded %s client applications for site", seeded)
        return {"seeded": seeded, "total": len(doc.client_apps or [])}

    # Back-compat alias used by older install hooks / buttons
    @classmethod
    def sync_installed_apps(cls, *, ignore_permissions: bool = False) -> dict[str, Any]:
        """Deprecated alias — seeds client apps (does not scan Frappe apps)."""
        if ignore_permissions:
            # install/scheduler path
            previous_user = frappe.session.user
            try:
                frappe.set_user("Administrator")
                return cls.seed_default_client_apps(replace=False)
            finally:
                frappe.set_user(previous_user)
        return cls.seed_default_client_apps(replace=False)
