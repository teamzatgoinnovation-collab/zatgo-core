"""Retail POS cash session: open / current / close, on ERPNext's POS Opening Entry and POS Closing Entry."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.services import pos_session_service as svc


@frappe.whitelist()
def current() -> dict[str, Any]:
    """The signed-in cashier's open session with running totals (`data: null` when none is open)."""
    return svc.current()


@frappe.whitelist(methods=["POST"])
def open(opening_cash: float | str = 0) -> dict[str, Any]:  # noqa: A001 - the endpoint is named "open"
    """Open a session with the cash float counted into the drawer. Idempotent: an open session is returned unchanged."""
    return svc.open_session(opening_cash)


@frappe.whitelist(methods=["POST"])
def close(counted_cash: float | str, opening_entry: str | None = None, counted: Any = None) -> dict[str, Any]:
    """Close the open session. counted_cash = cash counted in the drawer; `counted` = {mode_of_payment: amount} for other
    methods (default: the expected amount). Pass opening_entry to make a retry idempotent."""
    if isinstance(counted, str) and counted:
        counted = frappe.parse_json(counted)
    return svc.close_session(counted_cash, opening_entry, counted)
