"""Config History — configuration change snapshots."""

from __future__ import annotations

from frappe.model.document import Document


class ConfigHistory(Document):
    """Immutable-ish history row for settings mutations."""

    pass
