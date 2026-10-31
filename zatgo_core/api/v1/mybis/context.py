"""MyBis -- bootstrap context: who is asking, which companies and areas they may see, and the site's defaults and limits."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, getdate, today

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.mybis import period, scope
from zatgo_core.zatgo_core.doctype.zg_mybis_settings import zg_mybis_settings

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


def _precision(currency: str | None) -> int:
    """Decimals ERPNext keeps for an amount in `currency` on this site -- the rule of a Currency field: System Settings
    "Currency Precision" when set, else the decimals of the number format (the currency's own when the site uses it)."""
    configured = cint(frappe.db.get_default("currency_precision"))
    if configured:
        return configured
    try:
        from frappe.model.meta import get_precision_from_currency_format

        return cint(get_precision_from_currency_format(currency))
    except ImportError:  # a Frappe without the helper: the usual two decimals
        return 2


def _site_currency(companies: list[dict[str, Any]], default_company: str | None) -> str | None:
    """The currency to show before a company is chosen: the default company's, else the one every readable company shares."""
    by_name = {c["name"]: c["default_currency"] for c in companies}
    if default_company in by_name:
        return by_name[default_company] or None
    shared = {currency for currency in by_name.values() if currency}
    return shared.pop() if len(shared) == 1 else None


@frappe.whitelist(methods=["GET", "POST"])
def get_context() -> dict[str, Any]:
    """Everything the app needs after login. Reads nothing beyond what the user may read.

    Besides who and what (user, companies, areas) it carries the site's own settings, so the app assumes none: the period it opens
    on (`default_preset`), the first day of the week (`week_start`), the currency and decimals of amounts (`currency`,
    `currency_precision`, and `precision` per company) and the administrator's limits (`policy`, see ZG MyBis Settings)."""
    require_login()
    user = frappe.session.user
    companies = scope.readable_companies()
    areas = areas_for_user()
    default_company = _default_company([c["name"] for c in companies])
    return ok(
        {
            "user": user,
            "full_name": frappe.db.get_value("User", user, "full_name") or user,
            "companies": [
                {
                    "name": c["name"],
                    "abbr": c["abbr"],
                    "currency": c["default_currency"],
                    "precision": _precision(c["default_currency"]),
                    "country": c["country"],
                }
                for c in companies
            ],
            "default_company": default_company,
            "default_preset": zg_mybis_settings.default_preset(),
            "currency": _site_currency(companies, default_company),
            "currency_precision": _precision(None),
            "areas": areas,
            "has_access": bool(companies) and any(areas.values()),
            "presets": list(period.PRESETS),
            "week_start": scope.week_start(),
            "server_date": getdate(today()).isoformat(),
            "policy": zg_mybis_settings.policy(),
        }
    )


def _default_company(allowed: list[str]) -> str | None:
    default = (
        frappe.defaults.get_user_default("Company")
        or zg_mybis_settings.stored().get("default_company")
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
