"""Mixin that writes configuration changes to ZG Audit Log."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate, now_datetime, nowtime

from zatgo_core.constants.settings import DOCTYPES


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
        meta = self.meta
        request = getattr(frappe.local, "request", None)
        ip_address = getattr(request, "remote_addr", None) if request else None
        user_agent = (
            request.headers.get("User-Agent") if request and request.headers else None
        )
        now = now_datetime()

        for df in meta.fields:
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
            self._insert_audit_row(
                fieldname=fieldname,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
                browser=(user_agent or "")[:140],
                when=now,
            )

    def _insert_audit_row(
        self,
        *,
        fieldname: str,
        old_value: Any,
        new_value: Any,
        ip_address: str | None,
        browser: str,
        when,
    ) -> None:
        if not frappe.db.exists("DocType", DOCTYPES["AUDIT_LOG"]):
            return
        try:
            frappe.get_doc(
                {
                    "doctype": DOCTYPES["AUDIT_LOG"],
                    "doctype_name": self.doctype,
                    "document_name": self.name,
                    "fieldname": fieldname,
                    "old_value": self._stringify(old_value),
                    "new_value": self._stringify(new_value),
                    "changed_by": frappe.session.user,
                    "change_date": getdate(when),
                    "change_time": nowtime(),
                    "ip_address": ip_address,
                    "browser": browser,
                    "app_name": "zatgo_core",
                }
            ).insert(ignore_permissions=True)
        except Exception:
            frappe.logger("zatgo_core").exception("Failed to write audit log")

    @staticmethod
    def _stringify(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)
