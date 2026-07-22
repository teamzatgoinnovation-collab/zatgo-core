"""Chat AI health endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import fail, ok
from zatgo_core.api.validators import require_login


def _chat_ai_installed() -> bool:
    return "chat_ai" in frappe.get_installed_apps()


@frappe.whitelist()
def ping() -> dict[str, Any]:
    require_login()
    return status()


@frappe.whitelist()
def status() -> dict[str, Any]:
    require_login()
    if not _chat_ai_installed():
        return fail(
            "CHAT_AI_MISSING",
            "chat_ai app is not installed on this site",
        )
    count = 0
    if frappe.db.exists("DocType", "AI Chat Session"):
        count = frappe.db.count(
            "AI Chat Session",
            filters={"user": frappe.session.user, "status": "Active"},
        )
    return ok(
        {
            "product": "chat_ai",
            "title": "Chat AI",
            "ready": True,
            "stub": False,
            "count": count,
            "message": "Chat AI API ready",
            "domain": "chat",
        },
        meta={"stub": False, "count": count},
    )
