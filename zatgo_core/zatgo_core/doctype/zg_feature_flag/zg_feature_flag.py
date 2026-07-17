"""ZG Feature Flag controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.feature_flags import validate_feature_flag


class ZGFeatureFlag(AuditableMixin, CacheableSettingsMixin, Document):
    """Runtime feature toggle without code changes."""

    def validate(self) -> None:
        validate_feature_flag(self)
