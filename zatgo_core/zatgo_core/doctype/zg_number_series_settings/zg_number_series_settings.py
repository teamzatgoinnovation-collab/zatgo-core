"""ZG Number Series Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin
from zatgo_core.validation.number_series import validate_number_series


class ZGNumberSeriesSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Central numbering series registry for all ZatGo documents."""

    def validate(self) -> None:
        validate_number_series(self)
