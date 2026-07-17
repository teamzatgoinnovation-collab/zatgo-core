"""ZG Printer Settings controller."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin
from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


class ZGPrinterSettings(AuditableMixin, CacheableSettingsMixin, Document):
    """Global printer defaults for POS / kitchen / labels."""

    pass
