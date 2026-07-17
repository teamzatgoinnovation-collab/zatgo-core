"""Whitelisted settings APIs.

Paths:
  zatgo_core.api.v1.settings.get_system_settings
  zatgo_core.api.v1.settings.get_company_settings
  zatgo_core.api.v1.settings.get_branch_settings
  zatgo_core.api.v1.settings.get_user_preferences
  zatgo_core.api.v1.settings.save_settings
  zatgo_core.api.v1.settings.reload_settings
  zatgo_core.api.v1.settings.clear_cache
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import parse_json_dict, require_str
from zatgo_core.constants.settings import DOCTYPES
from zatgo_core.services.settings_service import SettingsService
from zatgo_core.utils.logging import log_api

_DOCTYPE_CATEGORY = {
    DOCTYPES["SYSTEM_SETTINGS"]: "system",
    DOCTYPES["COMPANY_SETTINGS"]: "company",
    DOCTYPES["BRANCH_SETTINGS"]: "branch",
    DOCTYPES["INTEGRATION_SETTINGS"]: "integrations",
    DOCTYPES["SECURITY_SETTINGS"]: "security",
    DOCTYPES["FEATURE_FLAG"]: "features",
    DOCTYPES["APPLICATION_SETTINGS"]: "apps",
    DOCTYPES["APPLICATION_REGISTRY"]: "apps",
    DOCTYPES["PRINTER_SETTINGS"]: "system",
    DOCTYPES["PAYMENT_SETTINGS"]: "system",
    DOCTYPES["NOTIFICATION_SETTINGS"]: "system",
    DOCTYPES["STORAGE_SETTINGS"]: "system",
    DOCTYPES["SYNC_SETTINGS"]: "system",
    DOCTYPES["NUMBER_SERIES_SETTINGS"]: "system",
    DOCTYPES["USER_PREFERENCES"]: "system",
}


@frappe.whitelist()
def get_system_settings() -> dict[str, Any]:
    """Return global ZG System Settings."""
    log_api("get_system_settings", user=frappe.session.user)
    return ok(SettingsService.get_system_settings())


@frappe.whitelist()
def get_company_settings(company: str) -> dict[str, Any]:
    """Return ZG Company Settings for a company."""
    company = require_str(company, "company")
    log_api("get_company_settings", user=frappe.session.user, company=company)
    return ok(SettingsService.get_company_settings(company))


@frappe.whitelist()
def get_branch_settings(branch: str) -> dict[str, Any]:
    """Return ZG Branch Settings by name."""
    branch = require_str(branch, "branch")
    log_api("get_branch_settings", user=frappe.session.user, branch=branch)
    return ok(SettingsService.get_branch_settings(branch))


@frappe.whitelist()
def get_user_preferences(user: str | None = None) -> dict[str, Any]:
    """Return preferences for a user (defaults to session user)."""
    log_api("get_user_preferences", user=frappe.session.user, target=user)
    return ok(SettingsService.get_user_preferences(user))


@frappe.whitelist()
def save_settings(
    doctype: str,
    values: Any,
    name: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Persist settings for a DocType (single or named document)."""
    doctype = require_str(doctype, "doctype")
    payload = parse_json_dict(values, "values")
    resolved_category = category or _DOCTYPE_CATEGORY.get(doctype, "system")
    log_api(
        "save_settings",
        user=frappe.session.user,
        doctype=doctype,
        name=name,
        category=resolved_category,
    )
    return ok(
        SettingsService.save_settings(
            doctype, payload, name=name, category=resolved_category
        )
    )


@frappe.whitelist()
def reload_settings(doctype: str | None = None) -> dict[str, Any]:
    """Reload settings documents and related caches."""
    log_api("reload_settings", user=frappe.session.user, doctype=doctype)
    return ok(SettingsService.reload_settings(doctype))


@frappe.whitelist()
def clear_cache() -> dict[str, Any]:
    """Clear all ZatGo Core caches."""
    log_api("clear_cache", user=frappe.session.user)
    return ok(SettingsService.clear_cache())
