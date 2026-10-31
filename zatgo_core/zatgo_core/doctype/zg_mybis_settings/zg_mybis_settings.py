"""ZG MyBis Settings controller -- defaults of the read-only MyBis dashboards (api/v1/mybis/context.py)."""

from __future__ import annotations

from frappe.model.document import Document

from zatgo_core.mixins.auditable import AuditableMixin


class ZGMyBisSettings(AuditableMixin, Document):
    pass
