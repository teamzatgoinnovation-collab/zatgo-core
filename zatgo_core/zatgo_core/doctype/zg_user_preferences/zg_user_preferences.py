"""ZG User Preferences controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class ZGUserPreferences(AuditableMixin, CacheableSettingsMixin, Document):
    """Per-user desk preferences for ZatGo applications."""

    pass
