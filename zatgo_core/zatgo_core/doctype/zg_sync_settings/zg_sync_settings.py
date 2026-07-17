"""ZG Sync Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class ZGSyncSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Offline sync and queue configuration."""

    pass
