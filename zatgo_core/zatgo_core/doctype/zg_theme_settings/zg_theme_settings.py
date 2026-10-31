"""ZG Theme Settings controller -- the brand and look of the ZatGo Desk theme (formerly fields of ZG System Settings).
Read through zatgo_core.services.ui_settings."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin


class ZGThemeSettings(AuditableMixin, Document):
    pass
