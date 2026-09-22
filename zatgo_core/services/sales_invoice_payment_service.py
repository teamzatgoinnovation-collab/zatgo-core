"""Cash / Credit payment automation for Sales Invoice.

`custom_payment_type` (patches/v0_2_2/add_payment_type_field.py) drives this:

- Cash: on submit, auto-create and submit a Payment Entry against the
  invoice using ERPNext's own get_payment_entry() helper (the same
  machinery the "Create > Payment" button in Desk uses) so GL postings,
  party account resolution, and exchange-rate handling all go through
  ERPNext's tested accounting code -- nothing here writes GL/stock rows
  directly. The Cash account comes from the "Cash" Mode of Payment's
  per-company default account (Mode of Payment Account), never hardcoded,
  so this works across companies that configure different Cash accounts.
- Credit: no Payment Entry. The invoice keeps its normal
  outstanding_amount, exactly as ERPNext would leave any invoice with no
  payment.

Duplicate-safe: before creating a Payment Entry, checks for an existing
*submitted* Payment Entry already referencing this Sales Invoice name.
An amended invoice gets a new document name, so this check naturally
starts clean for it -- ERPNext already requires an invoice's linked
Payment Entries be cancelled before the invoice itself can be cancelled
and amended, so there is nothing to reconcile here beyond keying off the
current doc's own name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

from zatgo_core.utils.logging import get_logger

if TYPE_CHECKING:
    from frappe.model.document import Document

logger = get_logger("system")

CASH_MODE_OF_PAYMENT = "Cash"


def create_cash_payment_entry(sales_invoice: Document) -> None:
    """Auto-create + submit a Payment Entry for a Cash-type Sales Invoice.

    No-ops for Credit / empty payment type, already-settled invoices, and
    invoices that already have a submitted Payment Entry against them.
    """
    if sales_invoice.doctype != "Sales Invoice" or sales_invoice.docstatus != 1:
        return

    payment_type = (sales_invoice.get("custom_payment_type") or "").strip()
    if payment_type != "Cash":
        return

    if frappe.utils.flt(sales_invoice.outstanding_amount) <= 0:
        logger.info(
            "Skipping auto Payment Entry for %s: outstanding_amount already 0",
            sales_invoice.name,
        )
        return

    if _has_submitted_payment_entry(sales_invoice.name):
        logger.info(
            "Skipping auto Payment Entry for %s: a submitted Payment Entry "
            "already references it",
            sales_invoice.name,
        )
        return

    cash_account = _get_cash_account(sales_invoice.company)

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    payment_entry = get_payment_entry(
        "Sales Invoice", sales_invoice.name, bank_account=cash_account
    )
    payment_entry.mode_of_payment = CASH_MODE_OF_PAYMENT
    payment_entry.insert(ignore_permissions=True)
    payment_entry.submit()

    logger.info(
        "Auto-created Payment Entry %s (Cash) for Sales Invoice %s",
        payment_entry.name,
        sales_invoice.name,
    )


def _has_submitted_payment_entry(sales_invoice_name: str) -> bool:
    return bool(
        frappe.db.exists(
            "Payment Entry Reference",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": sales_invoice_name,
                "docstatus": 1,
            },
        )
    )


def _get_cash_account(company: str) -> str:
    if not frappe.db.exists("Mode of Payment", CASH_MODE_OF_PAYMENT):
        frappe.throw(
            f"Cannot submit this Cash Sales Invoice: no 'Mode of Payment' named "
            f"'{CASH_MODE_OF_PAYMENT}' exists. Create it under Accounting > "
            f"Mode of Payment first."
        )

    cash_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": CASH_MODE_OF_PAYMENT, "company": company},
        "default_account",
    )
    if not cash_account:
        frappe.throw(
            f"Cannot submit this Cash Sales Invoice: the '{CASH_MODE_OF_PAYMENT}' "
            f"Mode of Payment has no default account configured for company "
            f"'{company}'. Add one under Mode of Payment > {CASH_MODE_OF_PAYMENT} "
            f"> Accounts, then re-submit."
        )
    return cash_account
