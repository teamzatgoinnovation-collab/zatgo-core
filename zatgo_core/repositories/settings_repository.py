"""Repository for reading/writing ZatGo Core settings documents."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.model.document import Document

from zatgo_core.constants.settings import DOCTYPES, SINGLE_SETTINGS


class SettingsRepository:
    """Persistence boundary for settings DocTypes."""

    @staticmethod
    def get_single(doctype: str) -> Document:
        if doctype not in SINGLE_SETTINGS:
            frappe.throw(frappe._("{0} is not a single settings DocType").format(doctype))
        if not frappe.db.exists(doctype, doctype):
            doc = frappe.get_doc({"doctype": doctype})
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            return doc
        return frappe.get_cached_doc(doctype, doctype)

    @staticmethod
    def get_by_filters(doctype: str, filters: dict[str, Any]) -> Document | None:
        name = frappe.db.exists(doctype, filters)
        if not name:
            return None
        return frappe.get_cached_doc(doctype, name)

    @staticmethod
    def list_docs(
        doctype: str,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        order_by: str = "modified desc",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return frappe.get_all(
            doctype,
            filters=filters or {},
            fields=fields or ["name", "modified"],
            order_by=order_by,
            limit_page_length=limit,
        )

    @staticmethod
    def save_single(doctype: str, values: dict[str, Any]) -> Document:
        doc = SettingsRepository.get_single(doctype)
        doc.update(values)
        doc.save(ignore_permissions=False)
        return doc

    @staticmethod
    def save_doc(doctype: str, name: str | None, values: dict[str, Any]) -> Document:
        if name and frappe.db.exists(doctype, name):
            doc = frappe.get_doc(doctype, name)
            doc.update(values)
            doc.save()
            return doc
        values = {**values, "doctype": doctype}
        doc = frappe.get_doc(values)
        doc.insert()
        return doc

    @staticmethod
    def ensure_user_preferences(user: str) -> Document:
        existing = frappe.db.exists(DOCTYPES["USER_PREFERENCES"], {"user": user})
        if existing:
            return frappe.get_doc(DOCTYPES["USER_PREFERENCES"], existing)
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPES["USER_PREFERENCES"],
                "user": user,
                "theme": "System",
            }
        )
        doc.insert(ignore_permissions=True)
        return doc
