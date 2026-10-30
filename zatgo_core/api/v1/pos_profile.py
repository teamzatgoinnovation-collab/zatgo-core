"""POS profile -- deliberately outside `resto_pos.` so it answers while the
Restaurant industry is off (the POS needs it to say so).

Path: zatgo_core.api.v1.pos_profile.get
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import resto_pos_admin_service as svc


@frappe.whitelist()
def get() -> dict[str, Any]:
    return svc.get_profile()
