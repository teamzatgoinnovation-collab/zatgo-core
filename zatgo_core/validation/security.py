"""Validation for ZG Security Settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

if TYPE_CHECKING:
    from frappe.model.document import Document


def validate_security_settings(doc: Document) -> None:
    """Enforce minimum security policy bounds."""
    if int(doc.min_password_length or 0) < 8:
        frappe.throw(frappe._("Min Password Length must be at least 8"))
    if int(doc.session_timeout_minutes or 0) < 5:
        frappe.throw(frappe._("Session Timeout must be at least 5 minutes"))
    if int(doc.login_limit or 0) < 1:
        frappe.throw(frappe._("Login Limit must be at least 1"))
