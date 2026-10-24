"""What a MyBis request is about: the company, the period and its comparison, validated against the caller's permissions.

Every MyBis endpoint starts with `resolve_scope(...)`. The company must be one the user may read (`row_scope.require_company`,
which honours Company User Permissions) -- an unnamed company falls back to the user's default and then to the only one they
can read, never to "all companies": figures of different companies are not mixed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import frappe
from frappe import _
from frappe.utils import getdate, today

from zatgo_core.services import row_scope
from zatgo_core.services.mybis import period as periods

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class Scope:
    company: str
    currency: str
    current: periods.Period
    previous: periods.Period | None
    preset: str

    def meta(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "currency": self.currency,
            "period": self.current.as_dict(),
            "previous_period": self.previous.as_dict() if self.previous else None,
            "preset": self.preset,
        }


def week_start() -> int:
    """Python weekday of the site's first day of the week (System Settings), Monday if unreadable."""
    try:
        name = (frappe.db.get_single_value("System Settings", "first_day_of_the_week") or "Monday").lower()
        return _WEEKDAYS.index(name)
    except Exception:
        return 0


def readable_companies() -> list[dict[str, Any]]:
    """Companies the user may read, with their currency (User Permissions applied by get_list).
    A user with no right to read Company at all has none -- the app then says so instead of failing."""
    try:
        return frappe.get_list(
            "Company",
            fields=["name", "abbr", "default_currency", "country"],
            order_by="name asc",
            limit_page_length=0,
        )
    except frappe.PermissionError:
        return []


def resolve_company(company: str | None) -> tuple[str, str]:
    """(company, currency) -- the named company if the user may read it, else their default, else their only one."""
    if company:
        row_scope.require_company(company)
        name = company
    else:
        allowed = readable_companies()
        names = [c["name"] for c in allowed]
        default = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        if default in names:
            name = default
        elif len(names) == 1:
            name = names[0]
        else:
            frappe.throw(_("Choose a company"), frappe.ValidationError)
    currency = frappe.get_cached_value("Company", name, "default_currency")
    if not currency:
        frappe.throw(_("Company {0} has no default currency").format(name), frappe.ValidationError)
    return name, currency


def _date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return getdate(value)
    except Exception:
        frappe.throw(_("Invalid date for {0}").format(field), frappe.ValidationError)


def resolve_scope(
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
) -> Scope:
    """Validate the caller's company / period input. Raises ValidationError / PermissionError on bad input."""
    name, currency = resolve_company(company)
    preset = preset or "this_month"
    try:
        current = periods.resolve(
            preset,
            getdate(today()),
            from_date=_date(from_date, "from_date"),
            to_date=_date(to_date, "to_date"),
            week_start=week_start(),
        )
    except ValueError as exc:
        frappe.throw(str(exc), frappe.ValidationError)
    want_compare = str(compare).lower() not in ("0", "false", "no", "")
    previous = periods.previous(preset, current, week_start=week_start()) if want_compare else None
    return Scope(name, currency, current, previous, preset)
