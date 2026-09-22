"""Sales Invoice on_submit: auto-settle Cash-type invoices.

See zatgo_core.services.sales_invoice_payment_service for the actual logic.
"""

from __future__ import annotations

from zatgo_core.services.sales_invoice_payment_service import create_cash_payment_entry


def on_submit(doc, method=None) -> None:
    create_cash_payment_entry(doc)
