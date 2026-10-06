"""Narration on Payment Entry / Journal Entry is never overwritten.

ERPNext regenerates PE `remarks` (set_remarks) and JE `remark`
(create_remarks) on every save unless the document's own "Custom
Remark(s)" flag is set. That flag is what we set here, so a narration the
user (or an API caller) wrote is kept, and an untouched auto-text still
follows the amounts as before. See patches/v0_2_5/add_narration_fields.py.

Only edits are detected server-side (the text differs from what is saved).
A new document's narration is flagged by the form script when the user
types it (public/js/payment_entry.js, journal_entry.js) or by zatgo_core's
own API when one is passed -- not guessed from "new + has text", because
ERPNext itself pre-fills `remark` on some JEs it creates internally
(invoice discounting, payment JEs) and those keep today's behaviour.
"""

from __future__ import annotations

NARRATION_FIELDS = {
    "Payment Entry": ("remarks", "custom_remarks"),
    "Journal Entry": ("remark", "custom_remark"),
}


def keep_user_narration(doc, method=None) -> None:
    """before_validate hook (runs before ERPNext rebuilds the remark)."""
    field, flag = NARRATION_FIELDS.get(doc.doctype, (None, None))
    if not field or doc.is_new() or not doc.has_value_changed(field):
        return
    # Written -> keep it; cleared -> hand the field back to ERPNext's auto-text.
    doc.set(flag, 1 if (doc.get(field) or "").strip() else 0)


def set_narration(doc, text: str | None) -> None:
    """For API code building a PE/JE: use `text` as its narration."""
    text = (text or "").strip()
    field, flag = NARRATION_FIELDS[doc.doctype]
    if text:
        doc.set(field, text)
        doc.set(flag, 1)
