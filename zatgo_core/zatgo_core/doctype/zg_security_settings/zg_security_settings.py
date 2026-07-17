"""ZG Security Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.security import validate_security_settings


class ZGSecuritySettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Password, session, and access-control policy."""

    def validate(self) -> None:
        validate_security_settings(self)
