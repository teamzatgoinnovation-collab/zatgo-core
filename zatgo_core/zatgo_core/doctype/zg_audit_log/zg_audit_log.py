"""ZG Audit Log controller."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class ZGAuditLog(Document):
    """Immutable audit trail entry (no client edits expected)."""

    def on_trash(self) -> None:
        if "System Manager" not in frappe.get_roles():
            frappe.throw(frappe._("Only System Manager can delete audit logs"))
