"""ZatGo modules on this site (read-only): which are enabled, installed, licensed, and what each needs."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services import module_settings


@frappe.whitelist()
def status() -> dict[str, Any]:
    require_login()
    return ok(module_settings.status())
