"""Numbers for the ZatGo ERP workspace block.

Path: zatgo_core.api.v1.erp_summary.get
"""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.services import erp_summary


@frappe.whitelist()
def get(period: str = "all") -> dict[str, Any]:
    return ok(erp_summary.summary(period))
