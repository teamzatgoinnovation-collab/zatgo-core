"""Subscription status for the Desk banner and the customer portal link (thin: logic is in services/subscription_gate)."""

from __future__ import annotations

import frappe

from zatgo_core.services import subscription_gate


@frappe.whitelist()
def get_status() -> dict:
    """The effective subscription picture of this site. Any logged-in user may read it (it is what the banner shows)."""
    return subscription_gate.boot_payload()
