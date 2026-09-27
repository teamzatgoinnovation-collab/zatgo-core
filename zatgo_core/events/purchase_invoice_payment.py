"""Purchase Invoice submit/cancel: Cash payment automation.

Mirrors events/sales_invoice_payment.py -- see
zatgo_core.services.invoice_cash_payment_service for the actual logic
(shared between both doctypes).
"""

from __future__ import annotations

from zatgo_core.services.invoice_cash_payment_service import (
    cancel_linked_payment_entries,
    create_cash_payment_entry,
)


def on_submit(doc, method=None) -> None:
    create_cash_payment_entry(doc)


def before_cancel(doc, method=None) -> None:
    cancel_linked_payment_entries(doc)
