"""The page of one ZatGo app (ZatGo sidebar > Apps > <app>): its tabs and its Overview.

Paths:
  zatgo_core.api.v1.app_page.get_app_page

Read by the Desk page `zg-app` (route `/desk/zg-app/<app>`). Real data only; what a user may open is decided
here on the server -- the Workspace's roles, then the same per-link permission check the Workspace page applies.
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import fail, ok
from zatgo_core.api.validators import require_str
from zatgo_core.services import app_page
from zatgo_core.services.ui_apps import asset_url

_STATUS = {"not_found": "not_found", "app_off": "app_off", "forbidden": "forbidden"}


@frappe.whitelist()
def get_app_page(key: str) -> dict[str, Any]:
    """The tabs and Overview of app `key` (the URL form, e.g. `vansalex`, `chat-ai`, `restaurant`)."""
    if frappe.session.user == "Guest":
        return fail("forbidden", "Login required")
    key = require_str(key, "key")
    try:
        data = app_page.build(key)
    except app_page.AppPageError as e:
        return fail(_STATUS.get(e.code, "not_found"), str(e))
    data["css"] = asset_url("css/zg_app.css")
    return ok(data)
