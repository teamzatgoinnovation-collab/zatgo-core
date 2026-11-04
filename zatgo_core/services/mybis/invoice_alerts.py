"""Tell the people who asked when a Sales or Purchase Invoice is submitted.

Registered as an extra `on_submit` hook (hooks.py) behind the MyBis switch. It must never be the reason an invoice fails to submit:
every error is caught, logged, and rolled back to a savepoint so a half-written notification cannot leave the transaction dirty.
Recipients are users who opted in (notify_prefs) and may read that very invoice (so Company User Permissions are honoured).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import fmt_money, flt

from zatgo_core.services import app_state
from zatgo_core.services.mybis import delivery, notify_prefs

# doctype -> (pref key, wording for a normal invoice, wording for a return)
KINDS = {
    "Sales Invoice": ("sales_invoice", "Sales invoice", "Sales return (credit note)", "customer", "customer_name"),
    "Purchase Invoice": ("purchase_invoice", "Purchase invoice", "Purchase return (debit note)", "supplier", "supplier_name"),
}


def message(doc: Any) -> tuple[str, str]:
    """(subject, body) for a submitted invoice -- pure, from the document's own fields."""
    _pref, normal, ret, party_field, name_field = KINDS[doc.doctype]
    label = ret if doc.get("is_return") else normal
    party = doc.get(name_field) or doc.get(party_field) or ""
    total = fmt_money(abs(flt(doc.get("grand_total"))), currency=doc.get("currency"))
    subject = f"{label} {doc.name}: {total}"
    lines = [f"{party} · {total}"]
    if flt(doc.get("outstanding_amount")) and not doc.get("is_return"):
        lines.append(_("Outstanding: {0}").format(fmt_money(flt(doc.outstanding_amount), currency=doc.get("currency"))))
    lines.append(f"{doc.company} · {doc.posting_date}")
    return subject, "\n".join(lines)


def on_submit(doc: Any, method: str | None = None) -> None:
    kind = KINDS.get(doc.doctype)
    if not kind or not app_state.is_on("mybis"):
        return
    point = "mybis_invoice_alert"
    try:
        frappe.db.savepoint(point)
        subject, body = message(doc)
        for user in notify_prefs.recipients(kind[0]):
            if user == frappe.session.user or not frappe.has_permission(doc.doctype, "read", doc=doc, user=user):
                continue
            delivery.notify(user, subject, body, doc.doctype, doc.name)
    except Exception:
        frappe.db.rollback(save_point=point)
        frappe.log_error(title="MyBis invoice alert failed", message=frappe.get_traceback())
