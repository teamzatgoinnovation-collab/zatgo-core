"""Whitelisted API for the Language Switcher Desk widget
(public/language_switcher/, switched on per site by ZG System Settings ->
Enable Language Switcher; formerly the separate language_switcher / modifyme app).

The source of truth for a user's language stays the native Frappe `User.language`
field — this module only exposes a small, safe way for the currently-logged-in
Desk user to read the supported languages and change their own preference.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.translate import get_all_languages

# The languages this app currently supports. Frappe recognizes many more — we
# deliberately scope to this fixed set rather than exposing every installed
# language, but the *display names* below are always looked up from Frappe's own
# Language doctype (get_all_languages), never hardcoded.
SUPPORTED_LANGUAGE_CODES = ("en", "ar")


@frappe.whitelist()
def get_supported_languages() -> list[dict]:
    """Return {language_code, language_name} for each supported, enabled language."""
    _require_login()

    names_by_code = {
        row["language_code"]: row["language_name"]
        for row in get_all_languages(with_language_name=True)
    }

    languages = []
    for code in SUPPORTED_LANGUAGE_CODES:
        if code in names_by_code:
            languages.append({"language_code": code, "language_name": names_by_code[code]})
        else:
            frappe.log_error(
                title="language_switcher: supported language missing or disabled",
                message=f"Language code '{code}' was not found (or not enabled) in the Language doctype.",
            )

    return languages


@frappe.whitelist()
def set_language(language: str) -> dict:
    """Set the current Desk user's own language preference. Never touches another user."""
    _require_login()
    language = _validate_supported_language(language)

    # frappe.session.user is resolved server-side from the authenticated session and is
    # never taken from client input, so this can only ever write the caller's own User doc.
    user = frappe.get_doc("User", frappe.session.user)
    user.language = language
    user.save(ignore_permissions=True)

    return {"language": language}


def _require_login() -> None:
    if frappe.session.user == "Guest":
        raise frappe.PermissionError(_("Authentication required"))


def _validate_supported_language(language: str) -> str:
    language = (language or "").strip()
    if language not in SUPPORTED_LANGUAGE_CODES:
        frappe.throw(_("Unsupported language: {0}").format(language))
    return language


def enable_supported_languages() -> None:
    """Frappe ships many Language records disabled. Only flip the native
    `enabled` flag on the supported ones so they can be picked -- the
    Language doctype stays the sole source of truth. Idempotent (runs on
    install and every migrate)."""
    for code in SUPPORTED_LANGUAGE_CODES:
        if frappe.db.exists("Language", code) and not frappe.db.get_value("Language", code, "enabled"):
            frappe.db.set_value("Language", code, "enabled", 1)
