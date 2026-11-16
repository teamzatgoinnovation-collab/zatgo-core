"""User-wise Sales Invoice print format (A4 / 80mm).

Extends the rule rows of `ZG Sales Invoice Naming Settings` (see
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


def is_80mm(fmt: str | None, rule: Any | None = None) -> bool:
    """True for the stock thermal format and for the rule's own 80mm format."""
    fmt = _clean(fmt)
    return bool(fmt) and (fmt == _fmt80_default() or (rule is not None and fmt == (rule.print_format_80mm or "")))


def resolve_print_format(user: str | None, company: str | None, requested: str | None) -> str:
    """The print format to render for `user`; "" means the site default.

    Raises PermissionError when the user is restricted and `requested` (or what
    their rule resolves it to) is not one of their assigned formats.
    """
    requested = _clean(requested)
    rule = find_rule(user, company)
    if not rule:
        return requested
    a4 = (rule.print_format_a4 or "").strip()
    mm = (rule.print_format_80mm or "").strip()
    restricted = bool(cint(rule.restrict_print_format)) and user not in EXEMPT_USERS

    final = requested
    if not requested:
        paper = rule.default_paper or (PAPER_80MM if mm and not a4 else PAPER_A4)
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
        a4, mm = row.print_format_a4 or "", row.print_format_80mm or ""
        if not (a4 or mm or cint(row.restrict_print_format)):
            continue
        out[row.company] = {
            "a4": a4,
            "mm": mm,
            "default": mm if (row.default_paper == PAPER_80MM or (mm and not a4)) else a4,
            "restrict": bool(cint(row.restrict_print_format)) and user not in EXEMPT_USERS,
        }
    return out


def validate_rule_formats(rules: list[Any]) -> None:
    """Settings.validate: assigned formats must be enabled Sales Invoice formats."""
    for row in rules:
        for label, fmt in (("A4 Print Format", row.print_format_a4), ("80mm Print Format", row.print_format_80mm)):
            if not fmt:
                continue
            info = frappe.db.get_value("Print Format", fmt, ["doc_type", "disabled"], as_dict=True)
            if not info:
                frappe.throw(f"Row #{row.idx} {label}: '{fmt}' does not exist.")
            if info.doc_type != "Sales Invoice" or cint(info.disabled):
                frappe.throw(f"Row #{row.idx} {label}: '{fmt}' must be an enabled Sales Invoice print format.")
        if row.default_paper == PAPER_A4 and not row.print_format_a4 and cint(row.restrict_print_format):
            frappe.throw(f"Row #{row.idx}: Default Paper A4 needs an A4 Print Format when restricted.")
        if row.default_paper == PAPER_80MM and not row.print_format_80mm and cint(row.restrict_print_format):
            frappe.throw(f"Row #{row.idx}: Default Paper 80mm needs an 80mm Print Format when restricted.")
        if cint(row.restrict_print_format) and not (row.print_format_a4 or row.print_format_80mm):
            frappe.throw(f"Row #{row.idx}: Restrict needs at least one print format.")
