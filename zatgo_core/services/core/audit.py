"""The one writer of Audit Log rows.

Every row says who changed what, when and from where. Callers decide what a row means: a settings field change
(mixins/auditable.py), a licence event (licensing/audit.py), an edition import (licensing/editions.py).
Never pass a secret: a Password field is written as "***" by the mixin, and licensing logs ids and hashes only.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import nowtime, today

from zatgo_core.constants.settings import DOCTYPES

DOCTYPE = DOCTYPES["AUDIT_LOG"]
_TEXT_LIMIT = 140  # the browser field


def _request_context() -> tuple[str | None, str | None]:
    request = getattr(frappe.local, "request", None)
    if not request:
        return None, None
    agent = request.headers.get("User-Agent") if getattr(request, "headers", None) else None
    return getattr(request, "remote_addr", None), (agent or "")[:_TEXT_LIMIT]


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def record(
    doctype: str,
    name: str | None,
    fieldname: str,
    old_value: Any = None,
    new_value: Any = None,
    *,
    reason: str = "",
    date: Any = None,
    strict: bool = False,
    durable: bool = False,
) -> None:
    """Write one Audit Log row for `doctype` / `name`.

    `strict`: let a failure raise (the caller's action must not succeed without its row); otherwise the failure is
    logged and the caller goes on. `durable`: the caller is about to raise, and Frappe rolls the request back on an
    error, so commit this row on its own (only inside a web request, never in tests or jobs).
    """
    ip_address, browser = _request_context()
    row = {
        "doctype": DOCTYPE,
        "doctype_name": doctype,
        "document_name": name or "",
        "fieldname": fieldname,
        "old_value": _text(old_value),
        "new_value": _text(new_value),
        "changed_by": frappe.session.user,
        "change_date": date or today(),
        "change_time": nowtime(),
        "ip_address": ip_address,
        "browser": browser,
        "reason": (reason or "")[:500] or None,
        "app_name": "zatgo_core",
    }
    try:
        if not frappe.db.exists("DocType", DOCTYPE):
            return
        frappe.get_doc(row).insert(ignore_permissions=True)
        if durable and getattr(frappe.local, "request", None) is not None and not frappe.flags.in_test:
            frappe.db.commit()  # nosemgrep: the audit row of a refusal that is about to roll the request back
    except Exception:
        if strict:
            raise
        frappe.logger("zatgo_core").exception("Audit Log write failed for %s %s", doctype, name)
