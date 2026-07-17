"""ZG Notification Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class ZGNotificationSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Notification channel configuration."""

    pass
