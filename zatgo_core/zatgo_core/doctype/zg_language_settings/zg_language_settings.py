"""ZG Language Settings controller -- the language options of the ZatGo language switcher (formerly a field of
ZG System Settings). Read through zatgo_core.services.ui_settings."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin


class ZGLanguageSettings(AuditableMixin, Document):
    pass
