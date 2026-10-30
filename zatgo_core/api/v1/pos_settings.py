"""ZatGo POS settings for the POS desktop app.

Path: zatgo_core.api.v1.pos_settings.get

Outside `resto_pos.` like pos_profile (the restaurant industry gate does not apply to it); the app switch does.
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.services import pos_settings
from zatgo_core.services.app_gate import app_api


@frappe.whitelist()
@app_api("zatgo_pos")
def get() -> dict[str, Any]:
    return ok(pos_settings.effective(), meta={"source": pos_settings.SETTINGS})
