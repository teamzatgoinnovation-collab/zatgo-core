"""Module Settings controller: switching ZatGo modules on and off (ADR-003). Rules live in services/module_settings.py."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.services import module_settings


class ModuleSettings(AuditableMixin, Document):
    def validate(self) -> None:
        module_settings.validate(self)

    def on_update(self) -> None:
        super().on_update()
        module_settings.apply_navigation()
