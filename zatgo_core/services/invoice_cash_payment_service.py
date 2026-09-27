"""Cash / Credit payment automation for Sales Invoice and Purchase Invoice.

`custom_payment_type` / `custom_cash_account` (patches/v0_2_2/add_payment_type_field.py
+ add_cash_account_field.py for Sales Invoice, patches/v0_2_3/add_purchase_invoice_payment_type_field.py
+ add_purchase_invoice_cash_account_field.py for Purchase Invoice) drive this:

- Cash: on submit, auto-create and submit a Payment Entry against the
  invoice using ERPNext's own get_payment_entry() helper (the same
  machinery the "Create > Payment" button in Desk uses) so GL postings,
  party account resolution, and exchange-rate handling all go through
  ERPNext's tested accounting code -- nothing here writes GL/stock rows
  directly. get_payment_entry() resolves payment direction itself
  (Receive for Sales Invoice, Pay for Purchase Invoice) and maps
  `bank_account` to the correct side (paid_to for a receive, paid_from
  for a pay) -- the same `custom_cash_account` field and code path work
  for both doctypes unmodified. The receiving/paying account is
  `custom_cash_account`, required whenever Payment Type = Cash -- a
  company can run more than one till/cash account, so the user (or an
  API caller) always picks the specific one. The client script pre-fills
  it from the "Cash" Mode of Payment's per-company default account as a
  starting suggestion (see public/js/sales_invoice.js,
  public/js/purchase_invoice.js) but that's just a UX convenience;
  nothing here falls back to it -- `mandatory_depends_on` on the field is
  a client-side-only hint in Frappe (confirmed:
  frappe.model.base_document._get_missing_mandatory_fields only ever
  looks at the static `reqd` flag), so the throw below is the actual
  enforcement, not a formality.
- Credit: no Payment Entry. The invoice keeps its normal
  outstanding_amount, exactly as ERPNext would leave any invoice with no
  payment.

On cancel (before_cancel, so it runs while the invoice's own docstatus is
still 1 in the database -- the same state a manual "cancel the Payment
Entry, then cancel the invoice" flow would see), any submitted Payment
Entry referencing the invoice is cancelled first through ERPNext's own
PaymentEntry.cancel() so GL reversal follows ERPNext's tested logic, not
a raw doc update. This isn't limited to Payment Entries this module
created -- ERPNext already refuses to cancel an invoice that has *any*
submitted Payment Entry against it (LinkExistsError from
check_no_back_links_exist(), which runs right after on_cancel), so
cascading the cancel here just turns an existing two-step manual
requirement into one action.

Duplicate-safe: before creating a Payment Entry, checks for an existing
*submitted* Payment Entry already referencing this invoice's name. An
amended invoice gets a new document name, so this check naturally starts
clean for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe

from zatgo_core.utils.logging import get_logger

if TYPE_CHECKING:
    from frappe.model.document import Document

logger = get_logger("system")

CASH_MODE_OF_PAYMENT = "Cash"
CASH_PAYMENT_DOCTYPES = ("Sales Invoice", "Purchase Invoice")


def create_cash_payment_entry(invoice: Document) -> None:
    """Auto-create + submit a Payment Entry for a Cash-type invoice.

    No-ops for Credit / empty payment type, already-settled invoices, and
    invoices that already have a submitted Payment Entry against them.
    """
    if invoice.doctype not in CASH_PAYMENT_DOCTYPES or invoice.docstatus != 1:
        return

    payment_type = (invoice.get("custom_payment_type") or "").strip()
    if payment_type != "Cash":
        return

    if frappe.utils.flt(invoice.outstanding_amount) <= 0:
        logger.info(
            "Skipping auto Payment Entry for %s: outstanding_amount already 0",
            invoice.name,
        )
        return

    if _has_submitted_payment_entry(invoice.doctype, invoice.name):
        logger.info(
            "Skipping auto Payment Entry for %s: a submitted Payment Entry "
            "already references it",
            invoice.name,
        )
        return

    cash_account = invoice.get("custom_cash_account")
    if not cash_account:
        frappe.throw(
            f"Cannot submit {invoice.name}: Payment Type is Cash but no "
            f"Cash Account was selected. Pick one in the Cash Account field "
            f"before submitting."
        )
    _validate_cash_account(cash_account, invoice.company)

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    payment_entry = get_payment_entry(invoice.doctype, invoice.name, bank_account=cash_account)
    payment_entry.mode_of_payment = CASH_MODE_OF_PAYMENT
    payment_entry.insert(ignore_permissions=True)
    payment_entry.submit()

    logger.info(
        "Auto-created Payment Entry %s (Cash) for %s %s",
        payment_entry.name,
        invoice.doctype,
        invoice.name,
    )


def cancel_linked_payment_entries(invoice: Document) -> None:
    """Cancel every submitted Payment Entry referencing this invoice.

    Called from before_cancel so it runs while the invoice's own row is
    still docstatus=1 in the database -- the same state ERPNext's own
    "cancel the Payment Entry before the invoice" manual requirement
    expects, and well before check_no_back_links_exist() (which fires
    from on_cancel) would otherwise block the invoice's own cancel.
    """
    if invoice.doctype not in CASH_PAYMENT_DOCTYPES:
        return

    payment_entry_names = frappe.get_all(
        "Payment Entry Reference",
        filters={
            "reference_doctype": invoice.doctype,
            "reference_name": invoice.name,
            "docstatus": 1,
        },
        pluck="parent",
        distinct=True,
    )

    for pe_name in payment_entry_names:
        payment_entry = frappe.get_doc("Payment Entry", pe_name)
        if payment_entry.docstatus != 1:
            continue
        payment_entry.flags.ignore_permissions = True
        payment_entry.cancel()
        logger.info(
            "Auto-cancelled Payment Entry %s (linked to cancelled %s %s)",
            pe_name,
            invoice.doctype,
            invoice.name,
        )


def _has_submitted_payment_entry(invoice_doctype: str, invoice_name: str) -> bool:
    return bool(
        frappe.db.exists(
            "Payment Entry Reference",
            {
                "reference_doctype": invoice_doctype,
                "reference_name": invoice_name,
                "docstatus": 1,
            },
        )
    )


def _validate_cash_account(account: str, company: str) -> None:
    row = frappe.db.get_value(
        "Account", account, ["company", "account_type", "is_group"], as_dict=True
    )
    if not row:
        frappe.throw(f"Cash account '{account}' does not exist.")
    if row.company != company:
        frappe.throw(
            f"Cash account '{account}' belongs to company '{row.company}', not "
            f"'{company}'. Pick a Cash Account that belongs to this invoice's company."
        )
    if row.is_group:
        frappe.throw(
            f"Cash account '{account}' is a group account and cannot receive "
            f"payments directly. Pick a specific ledger account."
        )
    if row.account_type != "Cash":
        frappe.throw(
            f"Cash account '{account}' is not a Cash-type account "
            f"(account_type={row.account_type!r}). Pick an account with "
            f"Account Type = Cash."
        )
