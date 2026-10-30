"""ZG System Settings controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class ZGSystemSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Global ERP foundation settings for the ZatGo ecosystem."""

    def onload(self) -> None:
        # Existing sites: show a row for every registered industry.
        from zatgo_core.industries.sync import ensure_rows

        ensure_rows(self)

    def validate(self) -> None:
        self._validate_defaults()
        from zatgo_core.industries.gate import validate_selection
        from zatgo_core.industries.sync import ensure_rows
        from zatgo_core.services.app_authority import assert_can_switch

        # Switching an app or an industry is a System Manager's call, whatever route the save took.
        assert_can_switch(self.get_doc_before_save(), self)
        ensure_rows(self)
        validate_selection({r.industry for r in self.enabled_industries if r.enabled})

    def on_update(self) -> None:
        # Audit trail + cache invalidation (the mixins) first.
        super().on_update()
        # Apps switched on / off: set up or take away their Desk entries now, not at the next migrate
        # (services/bundled_apps.py, services/app_desk.py).
        from zatgo_core.services import app_authority, app_state
        from zatgo_core.services.bundled_apps import BUNDLED, sync_bundled_apps

        before = self.get_doc_before_save()
        changed = app_authority.changed_switches(before, self)
        # /login and /vansalex depend on these: drop cached pages (incl. a
        # cached 404 for /vansalex from while it was off).
        if changed & {"saas_theme", "vansalex_web", "vansalex"}:
            from frappe.website.utils import clear_website_cache

            clear_website_cache()
        if changed:
            frappe.clear_document_cache(self.doctype, self.name)
        if changed & set(BUNDLED):
            sync_bundled_apps()
        if "language_switcher" in changed and app_state.is_on("language_switcher"):
            self._enable_arabic()
        # Industries switched on / off: roles, fields and Desk entries now.
        from zatgo_core.industries.sync import industries_changed, sync_industries

        if before is None or industries_changed(before, self):
            frappe.clear_document_cache(self.doctype, self.name)
            sync_industries()
        # Everything that mirrors the switches -- the Desk entries of in-core apps, the plugin registry, the
        # ZatGo sidebar -- after both syncs, so it sees the final state (a failure here must never block
        # saving the settings).
        if changed:
            self._refresh_app_views()
        try:
            from zatgo_core.services.app_desk import sync_rail_icons
            from zatgo_core.services.app_sidebar import sync_app_sidebars
            from zatgo_core.services.core_sidebar import sync_core_sidebar

            # `|`, not `or`: all must run (an app or industry switched on just made its rail icon / sidebar).
            if sync_core_sidebar() | sync_app_sidebars() | sync_rail_icons():
                frappe.clear_cache()
        except Exception:
            frappe.log_error(title="ZatGo: sidebar sync")

    @staticmethod
    def _enable_arabic() -> None:
        """The language switcher needs Arabic selectable; migrate does it too, but a switch flipped in the
        hub must not wait for the next migrate."""
        try:
            from zatgo_core.api.v1.language import enable_supported_languages

            enable_supported_languages()
        except Exception:
            frappe.log_error(title="ZatGo: enable Arabic for the language switcher")

    @staticmethod
    def _refresh_app_views() -> None:
        try:
            from zatgo_core.services.app_desk import sync_app_desk

            if sync_app_desk():
                frappe.clear_cache()
        except Exception:
            frappe.log_error(title="ZatGo: Desk entries of in-core apps")
        try:
            from zatgo_core.plugins.discover import discover_and_register_manifests

            discover_and_register_manifests()
        except Exception:
            frappe.log_error(title="ZatGo: app registry refresh")

    def _validate_defaults(self) -> None:
        if self.default_warehouse and self.default_company:
            warehouse_company = frappe.db.get_value(
                "Warehouse", self.default_warehouse, "company"
            )
            if warehouse_company and warehouse_company != self.default_company:
                frappe.throw(
                    frappe._("Default Warehouse must belong to Default Company")
                )
