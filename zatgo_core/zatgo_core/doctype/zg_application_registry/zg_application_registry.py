"""ZG Application Registry controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.app_registry import validate_app_registry


class ZGApplicationRegistry(AuditableMixin, CacheableSettingsMixin, Document):
    """Installed ZatGo application registry row."""

    def validate(self) -> None:
        validate_app_registry(self)
