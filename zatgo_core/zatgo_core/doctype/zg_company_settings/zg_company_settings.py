"""ZG Company Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.company_settings import validate_company_settings


class ZGCompanySettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Company-scoped configuration for ZatGo apps."""

    def validate(self) -> None:
        validate_company_settings(self)
