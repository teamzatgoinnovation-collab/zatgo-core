"""Audit Log controller: an append-only trail.

- Entries are written by the system only (the settings mixin, the licensing services -- always with
  `ignore_permissions`). One typed in through the Desk or REST is refused, so nobody can forge an entry.
- An existing entry is never changed, by any route.
- Deleting needs System Manager; licensing entries (editions, licences, issuing) cannot be deleted at all.
Install, migrate and patches (system code) are exempt.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

PROTECTED_DOCTYPES = frozenset({"Licence", "Licence History", "Edition", "Licence Config"})


def _system() -> bool:
    flags = frappe.flags
    return bool(flags.in_install or flags.in_migrate or flags.in_patch or flags.in_uninstall)


class AuditLog(Document):
    """Immutable audit trail entry."""

    def validate(self) -> None:
        if _system():
            return
        if not self.is_new():
            frappe.throw(_("Audit log entries cannot be changed."), frappe.PermissionError)
        if not self.flags.ignore_permissions:
            frappe.throw(_("Audit log entries are written by the system only."), frappe.PermissionError)

    def on_trash(self) -> None:
        if _system():
            return
        if self.doctype_name in PROTECTED_DOCTYPES:
            frappe.throw(_("Licensing audit entries cannot be deleted."), frappe.PermissionError)
        if "System Manager" not in frappe.get_roles():
            frappe.throw(_("Only System Manager can delete audit logs"))
