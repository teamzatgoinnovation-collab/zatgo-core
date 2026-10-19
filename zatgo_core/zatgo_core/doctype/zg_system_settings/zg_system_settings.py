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

        ensure_rows(self)
        validate_selection({r.industry for r in self.enabled_industries if r.enabled})

    def on_update(self) -> None:
        # Audit trail + cache invalidation (the mixins) first.
        super().on_update()
        # Bundled modules switched on / off: set up or take away their Desk
        # entries now, not at the next migrate (services/bundled_apps.py).
        from zatgo_core.services.bundled_apps import BUNDLED, sync_bundled_apps
        from zatgo_core.services.ui_apps import SWITCH_FIELDS

        before = self.get_doc_before_save()
        # /login and /vansalex depend on these: drop cached pages (incl. a
        # cached 404 for /vansalex from while it was off).
        if before is None or any(
            bool(self.get(f)) != bool(before.get(f)) for f in ("enable_saas_theme", "enable_vansalex_web")
        ):
            from frappe.website.utils import clear_website_cache

            clear_website_cache()
        if before is None or any(
            bool(self.get(SWITCH_FIELDS[key])) != bool(before.get(SWITCH_FIELDS[key])) for key in BUNDLED
        ):
            frappe.clear_document_cache(self.doctype, self.name)
            sync_bundled_apps()
        # Industries switched on / off: roles, fields and Desk entries now.
        from zatgo_core.industries.sync import industries_changed, sync_industries

        if before is None or industries_changed(before, self):
            frappe.clear_document_cache(self.doctype, self.name)
            sync_industries()

    def _validate_defaults(self) -> None:
        if self.default_warehouse and self.default_company:
            warehouse_company = frappe.db.get_value(
                "Warehouse", self.default_warehouse, "company"
            )
            if warehouse_company and warehouse_company != self.default_company:
                frappe.throw(
                    frappe._("Default Warehouse must belong to Default Company")
                )
