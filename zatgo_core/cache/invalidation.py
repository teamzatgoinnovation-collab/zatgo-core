"""Cache invalidation rules for settings DocTypes."""

from __future__ import annotations

import frappe

from zatgo_core.cache.manager import cache_manager
from zatgo_core.constants.settings import CACHE_KEYS, DOCTYPES, SINGLE_SETTINGS


def invalidate_settings_cache(doctype: str, name: str | None = None) -> None:
    """Invalidate Redis keys related to a settings DocType mutation."""
    mapping = {
        DOCTYPES["SYSTEM_SETTINGS"]: [CACHE_KEYS["SYSTEM"]],
        DOCTYPES["INTEGRATION_SETTINGS"]: [CACHE_KEYS["INTEGRATIONS"]],
        DOCTYPES["PRINTER_SETTINGS"]: [CACHE_KEYS["PRINTERS"]],
        DOCTYPES["FEATURE_FLAG"]: [CACHE_KEYS["FEATURE_FLAGS"]],
        DOCTYPES["APPLICATION_SETTINGS"]: [CACHE_KEYS["APP_REGISTRY"]],
        DOCTYPES["APPLICATION_REGISTRY"]: [CACHE_KEYS["APP_REGISTRY"]],
        DOCTYPES["PAYMENT_SETTINGS"]: ["payment_settings"],
        DOCTYPES["NOTIFICATION_SETTINGS"]: ["notification_settings"],
        DOCTYPES["STORAGE_SETTINGS"]: ["storage_settings"],
        DOCTYPES["SECURITY_SETTINGS"]: ["security_settings"],
        DOCTYPES["SYNC_SETTINGS"]: ["sync_settings"],
        DOCTYPES["NUMBER_SERIES_SETTINGS"]: ["number_series_settings"],
    }

    for key in mapping.get(doctype, []):
        cache_manager.delete(key)

    if doctype == DOCTYPES["COMPANY_SETTINGS"] and name:
        company = frappe.db.get_value(doctype, name, "company") or name
        cache_manager.delete(CACHE_KEYS["COMPANY"].format(company=company))

    if doctype == DOCTYPES["BRANCH_SETTINGS"] and name:
        cache_manager.delete(CACHE_KEYS["BRANCH"].format(branch=name))

    if doctype == DOCTYPES["USER_PREFERENCES"] and name:
        user = frappe.db.get_value(doctype, name, "user") or name
        cache_manager.delete(CACHE_KEYS["USER_PREFS"].format(user=user))

    # Also clear Frappe document cache for singles.
    if doctype in SINGLE_SETTINGS:
        try:
            frappe.clear_cache(doctype=doctype)
        except Exception:
            frappe.logger("zatgo_core").debug(
                "clear_cache failed for %s", doctype, exc_info=True
            )


def clear_all_core_cache() -> None:
    """Flush all ZatGo Core cache namespaces."""
    keys = [
        CACHE_KEYS["SYSTEM"],
        CACHE_KEYS["FEATURE_FLAGS"],
        CACHE_KEYS["APP_REGISTRY"],
        CACHE_KEYS["INTEGRATIONS"],
        CACHE_KEYS["PRINTERS"],
        "payment_settings",
        "notification_settings",
        "storage_settings",
        "security_settings",
        "sync_settings",
        "number_series_settings",
    ]
    cache_manager.delete_keys(*keys)
    frappe.clear_cache()
