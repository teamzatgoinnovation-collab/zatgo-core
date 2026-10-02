"""User-wise Sales Invoice naming series.

`ZG Sales Invoice Naming Settings` maps (user, company) to the naming series
that user's Sales Invoices and Sales Returns must use. This module is the one
place that rule is resolved and enforced. It runs from the Sales Invoice
`before_insert` hook (events/sales_invoice_naming.py), so the desk, REST
`/api/resource`, zatgo_core's own APIs (vansalex orders/returns,
erpnext_writes) and ERPNext's "Create > Return / Credit Note" all go through
it. The client never chooses: for a user with a rule, whatever naming_series
the request carried is overwritten.

Numbering itself stays Frappe's. We only set `naming_series`;
`set_name_by_naming_series` then turns it into a name through the row-locked
`tabSeries` counter (`getseries`: SELECT ... FOR UPDATE), so concurrent
inserts on one series serialise in the database and never share a number.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.model.naming import NamingSeries
from frappe.utils import cint

from zatgo_core.services.naming_series import counter_collision, get_naming_series_options

SETTINGS_DOCTYPE = "ZG Sales Invoice Naming Settings"
RULE_DOCTYPE = "ZG Sales Invoice Naming Rule"

UNMAPPED_USE_DEFAULT = "Use ERPNext default series"
UNMAPPED_BLOCK = "Block Sales Invoice creation"

# Scheduler jobs, Auto Repeat and Subscriptions create invoices as
# Administrator; "Block" must not stop the system's own invoicing.
EXEMPT_USERS = frozenset({"Administrator"})

NOT_CONFIGURED_MESSAGE = "Sales Invoice naming series is not configured for this user."


def get_settings() -> Any | None:
    """Cached settings doc, or None until `bench migrate` has created it."""
    if not frappe.db.table_exists(RULE_DOCTYPE):
        return None
    return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def find_rule(user: str | None, company: str | None) -> Any | None:
    settings = get_settings()
    if not settings or not user or not company:
        return None
    for row in settings.get("rules") or []:
        if cint(row.enabled) and row.user == user and row.company == company:
            return row
    return None


def get_user_sales_invoice_series(user: str | None, company: str | None, is_return: bool) -> str | None:
    """The series `user` must use in `company`, or None if no enabled rule."""
    rule = find_rule(user, company)
    if not rule:
        return None
    return rule.return_series if is_return else rule.normal_series


def blocks_unmapped_users() -> bool:
    settings = get_settings()
    return bool(settings) and settings.unmapped_user_behavior == UNMAPPED_BLOCK


def enforce_user_series(doc: Any) -> bool:
    """Set doc.naming_series from the session user's rule.

    Returns True when a rule applied. Returns False when the user has no rule
    and unmapped users fall back to ERPNext's own behaviour. Raises when the
    user has no rule and the settings block unmapped users, or when the rule
    points at a series that is no longer a Sales Invoice option (silently
    numbering from some other series is exactly what this feature prevents).
    """
    user = frappe.session.user
    company = doc.get("company")
    series = get_user_sales_invoice_series(user, company, bool(cint(doc.get("is_return"))))
    if not series:
        if user not in EXEMPT_USERS and blocks_unmapped_users():
            frappe.throw(
                f"{NOT_CONFIGURED_MESSAGE} (User: {user}, Company: {company or '-'}). "
                "Ask an administrator to add a rule in ZG Sales Invoice Naming Settings.",
                frappe.ValidationError,
                title="Naming Series Not Configured",
            )
        return False

    if series not in get_naming_series_options("Sales Invoice"):
        frappe.throw(
            f"The naming series '{series}' configured for {user} is no longer a Sales Invoice "
            "naming series. Ask an administrator to update ZG Sales Invoice Naming Settings.",
            frappe.ValidationError,
            title="Invalid Naming Series",
        )
    doc.naming_series = series
    return True


def get_session_user_series() -> dict[str, dict[str, str]]:
    """{company: {normal_series, return_series}} for the session user's enabled
    rules. Desk boot payload: lets the Sales Invoice form show the series the
    server is going to apply anyway."""
    settings = get_settings()
    if not settings:
        return {}
    user = frappe.session.user
    return {
        row.company: {"normal_series": row.normal_series, "return_series": row.return_series}
        for row in settings.get("rules") or []
        if cint(row.enabled) and row.user == user
    }


# -- configuration validation (ZG Sales Invoice Naming Settings.validate) -----


def series_prefix(series: str) -> str | None:
    """The tabSeries counter key a series increments (e.g. "S1-.##" -> "S1-").

    None for series whose prefix can't be evaluated without a document (e.g.
    .FY. with no Fiscal Year for today); those are left out of comparisons.
    """
    message_log = frappe.local.message_log
    mark = len(message_log)
    try:
        return NamingSeries(series).get_prefix()
    except Exception:
        # A frappe.throw inside the parser has already queued a msgprint;
        # this isn't an error the admin should see on save.
        del message_log[mark:]
        return None


def validate_rules(rules: list[Any]) -> None:
    """Throws on the first invalid rule row; normalises series whitespace."""
    options = get_naming_series_options("Sales Invoice")
    seen: dict[tuple[str, str], int] = {}

    for row in rules:
        row.normal_series = (row.normal_series or "").strip()
        row.return_series = (row.return_series or "").strip()
        where = f"Row #{row.idx}"

        key = (row.user, row.company)
        if key in seen:
            frappe.throw(
                f"{where}: {row.user} already has a rule for {row.company} (row #{seen[key]}). "
                "Edit that row instead of adding another."
            )
        seen[key] = row.idx

        for label, series in (("Invoice Series", row.normal_series), ("Return Series", row.return_series)):
            _validate_series(series, options, f"{where} {label}")

        if row.normal_series == row.return_series:
            frappe.throw(f"{where}: Invoice Series and Return Series must be different.")
        normal_prefix = series_prefix(row.normal_series)
        if normal_prefix and normal_prefix == series_prefix(row.return_series):
            frappe.throw(
                f"{where}: '{row.normal_series}' and '{row.return_series}' share the counter "
                f"'{normal_prefix}', so returns would take numbers from the invoice sequence. "
                "Use a distinct return prefix such as '-RET-'."
            )

    _validate_no_counter_collisions(rules, options)


def _validate_series(series: str, options: list[str], where: str) -> None:
    if not series:
        frappe.throw(f"{where} is required.")
    NamingSeries(series).validate()
    if series not in options:
        frappe.throw(
            f"{where}: '{series}' is not a Sales Invoice naming series. Add it under "
            "Selling Settings → Document Naming → Sales Invoice first."
        )


def _validate_no_counter_collisions(rules: list[Any], options: list[str]) -> None:
    rule_series = {s for row in rules for s in (row.normal_series, row.return_series)}
    prefixes = {s: series_prefix(s) for s in rule_series | set(options)}
    for a in sorted(rule_series):
        for b, prefix_b in prefixes.items():
            if counter_collision(prefixes[a], prefix_b):
                frappe.throw(
                    f"'{a}' and '{b}' use different counters that can produce the same "
                    f"invoice number ('{prefixes[a]}' vs '{prefix_b}'). Pick prefixes that "
                    "don't differ only by trailing digits."
                )
