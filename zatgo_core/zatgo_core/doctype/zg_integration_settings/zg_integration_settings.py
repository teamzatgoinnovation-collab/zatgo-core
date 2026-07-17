"""ZG Integration Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.integrations import validate_integration_settings


class ZGIntegrationSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """External integration credentials and toggles."""

    def validate(self) -> None:
        validate_integration_settings(self)
