"""Company document event hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

from zatgo_core.constants.settings import DOCTYPES

if TYPE_CHECKING:
    from frappe.model.document import Document


def on_company_update(doc: Document, method: str | None = None) -> None:
    """Ensure a ZG Company Settings row exists for every Company."""
    if not frappe.db.exists("DocType", DOCTYPES["COMPANY_SETTINGS"]):
        return
    if frappe.db.exists(DOCTYPES["COMPANY_SETTINGS"], {"company": doc.name}):
        return
    try:
        frappe.get_doc(
            {
                "doctype": DOCTYPES["COMPANY_SETTINGS"],
                "company": doc.name,
                "is_active": 1,
                "default_currency": doc.get("default_currency"),
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.logger("zatgo_core").exception(
            "Failed to create company settings for %s", doc.name
        )
