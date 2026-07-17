"""ZG Application Settings — site-wide Electron / Flutter / Web client config."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.application_settings import validate_application_settings


class ZGApplicationSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Single source of client-application settings for this ERPNext site."""

    def validate(self) -> None:
        validate_application_settings(self)
