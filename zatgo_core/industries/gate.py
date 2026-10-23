"""Per-site industry activation and its enforcement.

State lives in the site's own database: ZG System Settings -> Industries
(`enabled_industries`, child DocType ZG Enabled Industry). Nothing is on by
default and nothing is hard-coded per site.

Effective access = Frappe role permission AND industry switched on:
- `is_enabled` / `require_industry` / `@industry_api` for server code,
- `industry_doc_has_permission` / `industry_query_conditions` (the "*"
  permission hooks) make an industry's DocTypes nobody's while it is off,
- `gate_industry_api` (before_request) answers 404 for its whitelisted methods,
- `guard_job` for scheduled jobs.
Everything fails closed: unreadable settings = every industry off. The "*"
hooks never return None (Frappe reads falsy as denial) and do no meta loads.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

import frappe
from frappe import _

from zatgo_core.industries import registry

SETTINGS = "ZG System Settings"
TABLE_FIELD = "enabled_industries"


def enabled_keys() -> set[str]:
    """Industries switched on for this site."""
    try:
        doc = frappe.get_cached_doc(SETTINGS)
    except Exception:
        return set()
    return {
        row.industry
        for row in (doc.get(TABLE_FIELD) or [])
        if row.enabled and row.industry in registry.INDUSTRIES and registry.INDUSTRIES[row.industry].implemented
    }


def is_enabled(key: str) -> bool:
    return key in enabled_keys()


def require_industry(key: str) -> None:
    if not is_enabled(key):
        frappe.throw(_("The {0} industry is not enabled on this site.").format(key), frappe.PermissionError)


def industry_api(key: str, roles: tuple[str, ...] = ()) -> Callable:
    """Decorator for an industry's whitelisted method, under @frappe.whitelist():
    authenticated, industry on, and (when `roles` is given) one of those roles
    or System Manager. DocType permissions still apply inside."""

    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if frappe.session.user == "Guest":
                frappe.throw(_("Login required"), frappe.AuthenticationError)
            require_industry(key)
            if roles and not (set(frappe.get_roles()) & (set(roles) | {"System Manager"})):
                frappe.throw(_("Not permitted"), frappe.PermissionError)
            return fn(*args, **kwargs)

        return wrapper

    return deco


def guard_job(key: str) -> bool:
    """First line of an industry's scheduled job: `if not guard_job(k): return`."""
    return is_enabled(key)


# -- hooks ---------------------------------------------------------------------


def industry_doc_has_permission(doc, ptype=None, user=None):
    owner = registry.doctype_owner().get(getattr(doc, "doctype", None))
    return True if owner is None else is_enabled(owner)


def industry_query_conditions(user=None, doctype=None):
    owner = registry.doctype_owner().get(doctype) if doctype else None
    return "1=0" if owner is not None and not is_enabled(owner) else ""


def _prefixes() -> dict[str, tuple[str, ...]]:
    return {k: i.api_prefixes for k, i in registry.INDUSTRIES.items() if i.api_prefixes}


def gate_industry_api() -> None:
    """before_request: a whitelisted method of a switched-off industry -> 404."""
    from zatgo_core.services.app_gate import requested_method

    method = requested_method()
    if not method:
        return
    for key, prefixes in _prefixes().items():
        if method.startswith(prefixes) and not is_enabled(key):
            raise frappe.DoesNotExistError(f"{method} is not available on this site")


# -- selection rules -----------------------------------------------------------


def validate_selection(selected: set[str]) -> None:
    """Throw on an invalid combination: unknown / not yet implemented
    industries, a missing core capability, or a missing industry dependency."""
    for key in sorted(selected):
        ind = registry.get(key)
        if ind is None:
            frappe.throw(_("Unknown industry: {0}").format(key))
        if not ind.implemented:
            frappe.throw(_("{0} is not available yet.").format(ind.label))
        for cap in ind.requires:
            if not frappe.db.exists("DocType", registry.CAPABILITIES[cap]):
                frappe.throw(_("{0} needs the {1} module, which is not installed.").format(ind.label, cap))
        for dep in ind.requires_industries:
            if dep not in selected:
                frappe.throw(
                    _("{0} requires the {1} industry to be enabled.").format(ind.label, registry.INDUSTRIES[dep].label)
                )
