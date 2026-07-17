"""ZG Branch Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.branch_settings import validate_branch_settings


class ZGBranchSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Branch-scoped operational configuration."""

    def validate(self) -> None:
        validate_branch_settings(self)
