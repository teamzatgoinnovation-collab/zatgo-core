"""ZG System Settings controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class ZGSystemSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Global ERP foundation settings for the ZatGo ecosystem."""

    def validate(self) -> None:
        self._validate_defaults()

    def _validate_defaults(self) -> None:
        if self.default_warehouse and self.default_company:
            warehouse_company = frappe.db.get_value(
                "Warehouse", self.default_warehouse, "company"
            )
            if warehouse_company and warehouse_company != self.default_company:
                frappe.throw(
                    frappe._("Default Warehouse must belong to Default Company")
                )
