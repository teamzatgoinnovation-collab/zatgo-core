"""User-wise Sales Invoice print format (A4 / 80mm).

Extends the rule rows of `Sales Invoice Naming Settings` (see
services/sales_invoice_naming.py): a rule may name an A4 and an 80mm Print
Format for its (user, company), a default paper, and a Restrict flag.

Resolution is server-side and shared by every print path we own -- the
VanSaleX PDF API and the Desk print/PDF entry points
(overrides/print_entry.py) -- so the client never decides what a restricted
user may print. Users without a rule, and Administrator, are untouched.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from zatgo_core.services.sales_invoice_naming import EXEMPT_USERS, find_rule, get_settings

PAPER_A4 = "A4"
PAPER_80MM = "80mm"
STANDARD = "Standard"  # Desk's "no custom format" choice


def _fmt80_default() -> str:
    from zatgo_core.setup.ensure_print_formats import PRINT_FORMAT_80MM_NAME

    return PRINT_FORMAT_80MM_NAME


def _clean(value: str | None) -> str:
    value = (value or "").strip()
    return "" if value == STANDARD else value


def site_formats() -> tuple[str, str]:
    """(A4, 80mm) print formats set for the whole site in ZatGo Sales Invoice Naming
    Settings; "" where unset. ERPNext's default Sales Invoice format can itself be an
    80mm one, so A4 is never guessed from it once this is set."""
    settings = get_settings()
    if not settings:
        return "", ""
    return (settings.get("default_print_format_a4") or "").strip(), (settings.get("default_print_format_80mm") or "").strip()


def is_80mm(fmt: str | None, rule: Any | None = None) -> bool:
    """True for the stock thermal format, the site's 80mm format and the rule's own."""
    fmt = _clean(fmt)
    if not fmt:
        return False
    own = (rule.get("print_format_80mm") or "") if rule is not None else ""
    return fmt in (_fmt80_default(), site_formats()[1], own)


def restricted_rule(rule: Any, user: str | None) -> bool:
    return bool(cint(rule.get("restrict_print_format"))) and user not in EXEMPT_USERS


def resolve_print_format(user: str | None, company: str | None, requested: str | None) -> str:
    """The print format to render for `user`; "" means the site default.

    Raises PermissionError when the user is restricted and `requested` (or what
    their rule resolves it to) is not one of their assigned formats.
    """
    requested = _clean(requested)
    site_a4, site_mm = site_formats()
    rule = find_rule(user, company)
    if not rule:
        # No rule: the site's own A4 / 80mm choice, when set, stands in for the
        # app's "A4" (blank) and stock 80mm requests.
        if not requested:
            return site_a4
        if requested == _fmt80_default() and site_mm:
            return site_mm
        return requested
    a4 = (rule.get("print_format_a4") or "").strip() or ("" if restricted_rule(rule, user) else site_a4)
    mm = (rule.get("print_format_80mm") or "").strip() or ("" if restricted_rule(rule, user) else site_mm)
    restricted = restricted_rule(rule, user)

    final = requested
    if not requested:
        paper = rule.get("default_paper") or (PAPER_80MM if mm and not a4 else PAPER_A4)
        final = mm if paper == PAPER_80MM else a4
    elif requested == _fmt80_default() and mm:
        # VanSaleX's 80mm choice: use this user's own 80mm layout.
        final = mm

    if restricted and (not final or final not in (a4, mm)):
        frappe.throw(
            _("You may only print Sales Invoices with your assigned print format."),
            frappe.PermissionError,
        )
    return final


def session_site_formats() -> dict[str, str]:
    """Site-wide formats for the Desk print dialog: the site's own choice, else stock 80mm."""
    a4, mm = site_formats()
    return {"a4": a4, "mm": mm or _fmt80_default()}


def session_print_config() -> dict[str, dict[str, Any]]:
    """{company: {a4, mm, default, restrict}} for the session user, for Desk boot."""
    settings = get_settings()
    if not settings:
        return {}
    user = frappe.session.user
    out: dict[str, dict[str, Any]] = {}
    for row in settings.get("rules") or []:
        if not cint(row.enabled) or row.user != user:
            continue
        a4, mm = row.get("print_format_a4") or "", row.get("print_format_80mm") or ""
        if not (a4 or mm or cint(row.get("restrict_print_format"))):
            continue
        out[row.company] = {
            "a4": a4,
            "mm": mm,
            "default": mm if (row.get("default_paper") == PAPER_80MM or (mm and not a4)) else a4,
            "restrict": bool(cint(row.get("restrict_print_format"))) and user not in EXEMPT_USERS,
        }
    return out


def validate_rule_formats(rules: list[Any]) -> None:
    """Settings.validate: assigned formats must be enabled Sales Invoice formats."""
    for row in rules:
        for label, fmt in (("A4 Print Format", row.get("print_format_a4")), ("80mm Print Format", row.get("print_format_80mm"))):
            if not fmt:
                continue
            info = frappe.db.get_value("Print Format", fmt, ["doc_type", "disabled"], as_dict=True)
            if not info:
                frappe.throw(f"Row #{row.idx} {label}: '{fmt}' does not exist.")
            if info.doc_type != "Sales Invoice" or cint(info.disabled):
                frappe.throw(f"Row #{row.idx} {label}: '{fmt}' must be an enabled Sales Invoice print format.")
        if row.get("default_paper") == PAPER_A4 and not row.get("print_format_a4") and cint(row.get("restrict_print_format")):
            frappe.throw(f"Row #{row.idx}: Default Paper A4 needs an A4 Print Format when restricted.")
        if row.get("default_paper") == PAPER_80MM and not row.get("print_format_80mm") and cint(row.get("restrict_print_format")):
            frappe.throw(f"Row #{row.idx}: Default Paper 80mm needs an 80mm Print Format when restricted.")
        if cint(row.get("restrict_print_format")) and not (row.get("print_format_a4") or row.get("print_format_80mm")):
            frappe.throw(f"Row #{row.idx}: Restrict needs at least one print format.")
