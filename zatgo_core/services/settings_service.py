"""Settings orchestration service — single source of truth for consumers."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.cache.invalidation import clear_all_core_cache
from zatgo_core.cache.manager import cache_manager
from zatgo_core.constants.settings import CACHE_KEYS, DOCTYPES, SINGLE_SETTINGS
from zatgo_core.permissions.guards import assert_can_write_settings, assert_can_read_settings
from zatgo_core.repositories.settings_repository import SettingsRepository
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")


class SettingsService:
    """High-level settings API used by whitelisted methods and other apps."""

    @staticmethod
    def get_system_settings() -> dict[str, Any]:
        assert_can_read_settings("system")
        return cache_manager.get_or_set(
            CACHE_KEYS["SYSTEM"],
            lambda: SettingsRepository.get_single(DOCTYPES["SYSTEM_SETTINGS"]).as_dict(),
        )

    @staticmethod
    def get_company_settings(company: str) -> dict[str, Any] | None:
        assert_can_read_settings("company")
        if not company:
            frappe.throw(frappe._("Company is required"))
        key = CACHE_KEYS["COMPANY"].format(company=company)

        def _load() -> dict[str, Any] | None:
            doc = SettingsRepository.get_by_filters(
                DOCTYPES["COMPANY_SETTINGS"], {"company": company}
            )
            return doc.as_dict() if doc else None

        return cache_manager.get_or_set(key, _load)

    @staticmethod
    def get_branch_settings(branch: str) -> dict[str, Any] | None:
        assert_can_read_settings("branch")
        if not branch:
            frappe.throw(frappe._("Branch is required"))
        key = CACHE_KEYS["BRANCH"].format(branch=branch)

        def _load() -> dict[str, Any] | None:
            if not frappe.db.exists(DOCTYPES["BRANCH_SETTINGS"], branch):
                return None
            return frappe.get_cached_doc(DOCTYPES["BRANCH_SETTINGS"], branch).as_dict()

        return cache_manager.get_or_set(key, _load)

    @staticmethod
    def get_user_preferences(user: str | None = None) -> dict[str, Any]:
        user = user or frappe.session.user
        if user != frappe.session.user and "System Manager" not in frappe.get_roles():
            frappe.throw(frappe._("Not permitted to read preferences for another user"))
        key = CACHE_KEYS["USER_PREFS"].format(user=user)

        def _load() -> dict[str, Any]:
            return SettingsRepository.ensure_user_preferences(user).as_dict()

        return cache_manager.get_or_set(key, _load)

    @staticmethod
    def get_integrations() -> dict[str, Any]:
        assert_can_read_settings("integrations")
        return cache_manager.get_or_set(
            CACHE_KEYS["INTEGRATIONS"],
            lambda: SettingsRepository.get_single(
                DOCTYPES["INTEGRATION_SETTINGS"]
            ).as_dict(),
        )

    @staticmethod
    def get_printers() -> dict[str, Any]:
        assert_can_read_settings("system")
        return cache_manager.get_or_set(
            CACHE_KEYS["PRINTERS"],
            lambda: SettingsRepository.get_single(DOCTYPES["PRINTER_SETTINGS"]).as_dict(),
        )

    @staticmethod
    def save_settings(
        doctype: str,
        values: dict[str, Any],
        *,
        name: str | None = None,
        category: str = "system",
    ) -> dict[str, Any]:
        assert_can_write_settings(category)
        if doctype in SINGLE_SETTINGS:
            doc = SettingsRepository.save_single(doctype, values)
        else:
            doc = SettingsRepository.save_doc(doctype, name, values)
        logger.info("Saved settings doctype=%s name=%s", doctype, doc.name)
        return doc.as_dict()

    @staticmethod
    def reload_settings(doctype: str | None = None) -> dict[str, Any]:
        assert_can_read_settings("system")
        if doctype:
            frappe.clear_cache(doctype=doctype)
            if doctype in SINGLE_SETTINGS:
                return SettingsRepository.get_single(doctype).as_dict()
            return {"doctype": doctype, "reloaded": True}
        clear_all_core_cache()
        return {"reloaded": True, "scope": "all"}

    @staticmethod
    def clear_cache() -> dict[str, Any]:
        assert_can_write_settings("system")
        clear_all_core_cache()
        logger.info("Cleared ZatGo Core cache by %s", frappe.session.user)
        return {"cleared": True}
