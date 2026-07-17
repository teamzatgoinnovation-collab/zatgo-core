"""Project Tracker status via the zatgo_core hub."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login


@frappe.whitelist()
def ping() -> dict[str, Any]:
    """Confirm hub routing for Project Tracker clients."""
    require_login()
    installed = "project_tracker" in frappe.get_installed_apps()
    return ok(
        {
            "product": "project_tracker",
            "title": "Project Tracker",
            "ready": installed,
            "stub": False,
            "installed": installed,
            "message": (
                "Use project_tracker.api.v1.* for CRUD. "
                "This hub method only reports install status."
            ),
            "crud_namespace": "project_tracker.api.v1",
        },
        meta={"stub": False, "live_app": "project_tracker"},
    )


@frappe.whitelist()
def status() -> dict[str, Any]:
    """Alias of ping for consistency with other product packages."""
    return ping()
