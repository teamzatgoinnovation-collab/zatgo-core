"""ZG Config History — configuration change snapshots."""

from __future__ import annotations

from frappe.model.document import Document


class ZGConfigHistory(Document):
    """Immutable-ish history row for settings mutations."""

    pass
