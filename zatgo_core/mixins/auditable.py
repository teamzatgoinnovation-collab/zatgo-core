"""Mixin that writes configuration changes to Audit Log."""

from __future__ import annotations

from typing import Any

from frappe.utils import getdate, now_datetime

from zatgo_core.constants.settings import DOCTYPES
from zatgo_core.services.core import audit


class AuditableMixin:
    """Track field-level configuration changes for settings DocTypes."""

    def on_update(self) -> None:
        if not getattr(self.flags, "ignore_zg_audit", False):
            if self.doctype != DOCTYPES["AUDIT_LOG"]:
                self._write_audit_entries()
        try:
            super().on_update()
        except AttributeError:
            # Frappe Document may not define an empty on_update hook.
            pass

    def _write_audit_entries(self) -> None:
        now = now_datetime()
        for df in self.meta.fields:
            if df.fieldtype in (
                "Section Break",
                "Column Break",
                "Tab Break",
                "HTML",
                "Button",
                "Fold",
                "Heading",
                "Table",
                "Table MultiSelect",
            ):
                continue
            fieldname = df.fieldname
            if not self.has_value_changed(fieldname):
                continue
            old_value = self.get_db_value(fieldname) if not self.is_new() else None
            new_value = self.get(fieldname)
            if df.fieldtype == "Password":
                old_value = "***" if old_value else None
                new_value = "***" if new_value else None
            self._insert_audit_row(fieldname=fieldname, old_value=old_value, new_value=new_value, when=now)

    def _insert_audit_row(self, *, fieldname: str, old_value: Any, new_value: Any, when=None, **_ignored: Any) -> None:
        """One row through services/core/audit.py, which adds the user, time, IP address and browser of the request.
        `ip_address` / `browser` are still accepted from older callers and ignored."""
        audit.record(self.doctype, self.name, fieldname, old_value, new_value, date=getdate(when) if when else None)
