"""Ensure the Mode of Payment records Resto POS checkout depends on exist."""

from __future__ import annotations

import frappe

from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

# (name, ERPNext "type") — matches the naming already used by
# `ZG Delivery Stop.payment_method` (Cash/COD/Card/Online/Wallet).
_MODES = (
    ("Cash", "Cash"),
    ("Card", "Bank"),
    ("Wallet", "General"),
)


def ensure_mode_of_payment() -> None:
    """Create missing Mode of Payment records (idempotent)."""
    for name, mop_type in _MODES:
        if frappe.db.exists("Mode of Payment", name):
            continue
        frappe.get_doc(
            {
                "doctype": "Mode of Payment",
                "mode_of_payment": name,
                "type": mop_type,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        logger.info("Created Mode of Payment %s", name)
