"""MyBis -- bootstrap context: who is asking, which companies and areas they may see."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate, today

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.mybis import period, scope

# MyBis area -> the DocType whose read permission opens it. ERPNext permissions are the final authority; the app
# only hides what the server would refuse anyway.
AREAS = {
    "sales": "Sales Invoice",
    "purchases": "Purchase Invoice",
    "inventory": "Bin",
    "customers": "Customer",
    "suppliers": "Supplier",
    "finance": "GL Entry",
    "products": "Item",
    "reports": "GL Entry",
}


def areas_for_user() -> dict[str, bool]:
    return {area: bool(frappe.has_permission(doctype, "read")) for area, doctype in AREAS.items()}


@frappe.whitelist(methods=["GET", "POST"])
def get_context() -> dict[str, Any]:
    """Everything the app needs after login. Reads nothing beyond what the user may read."""
    require_login()
    user = frappe.session.user
    companies = scope.readable_companies()
    areas = areas_for_user()
    return ok(
        {
            "user": user,
            "full_name": frappe.db.get_value("User", user, "full_name") or user,
            "companies": [
                {"name": c["name"], "abbr": c["abbr"], "currency": c["default_currency"], "country": c["country"]}
                for c in companies
            ],
            "default_company": _default_company([c["name"] for c in companies]),
            "default_preset": _default_preset(),
            "areas": areas,
            "has_access": bool(companies) and any(areas.values()),
            "presets": list(period.PRESETS),
            "week_start": scope.week_start(),
            "server_date": getdate(today()).isoformat(),
        }
    )


def _mybis_setting(field: str) -> str | None:
    try:
        return frappe.db.get_single_value("ZG MyBis Settings", field) or None
    except Exception:  # not migrated yet: no settings table
        return None


def _default_preset() -> str:
    preset = _mybis_setting("default_preset")
    return preset if preset in period.PRESETS else "this_month"


def _default_company(allowed: list[str]) -> str | None:
    default = (
        frappe.defaults.get_user_default("Company")
        or _mybis_setting("default_company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )
    if default in allowed:
        return default
    return allowed[0] if len(allowed) == 1 else None


@frappe.whitelist(methods=["GET", "POST"])
def resolve_period(
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
) -> dict[str, Any]:
    """The concrete dates (and comparison dates) a preset means on this site -- one definition for every client."""
    require_login()
    return ok(scope.resolve_scope(company, preset, from_date, to_date, compare).meta())
