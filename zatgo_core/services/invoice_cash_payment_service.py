"""Cash / Bank / Credit payment automation for Sales Invoice and Purchase Invoice.

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
- Bank (patches/v0_2_7/add_bank_payment_fields.py for Sales Invoice,
  patches/v0_2_8/add_purchase_invoice_bank_payment_fields.py for Purchase
  Invoice): the same as Cash, via `custom_bank_account` (Account Type = Bank,
  required). ERPNext requires a reference no. and date on every bank
  Payment Entry: `custom_bank_reference_no` (transfer / cheque no.), else
  the invoice number, dated the invoice's posting date. Mode of Payment is
  the Bank-type one whose company default account is that bank account,
  when there is exactly one.
- Credit: no Payment Entry. The invoice keeps its normal
  outstanding_amount, exactly as ERPNext would leave any invoice with no
  payment.

On cancel (before_cancel, so it runs while the invoice's own docstatus is
still 1 in the database -- the same state a manual "cancel the Payment
Entry, then cancel the invoice" flow would see), a submitted Payment Entry
that pays this invoice and nothing else (the auto Cash / Bank one, or any
one-invoice payment with no advance left on it) is cancelled first through
ERPNext's own PaymentEntry.cancel() so GL reversal follows ERPNext's tested
logic, not a raw doc update. A Payment Entry that also settles other
invoices or holds an advance (a VanSaleX collection, a bulk receipt) is
never cancelled here -- that would reverse money really received and
reopen the other invoices; ERPNext's own on_cancel unlinks the invoice
from it instead (Accounts Settings "Unlink Payment on Cancellation of
Invoice"), or refuses the cancel when that setting is off.

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
# Payment Type -> (invoice account field, its label, required Account Type)
AUTO_PAYMENT_TYPES = {
    "Cash": ("custom_cash_account", "Cash Account", "Cash"),
    "Bank": ("custom_bank_account", "Bank Account", "Bank"),
}


def create_cash_payment_entry(invoice: Document) -> None:
    """Auto-create + submit a Payment Entry for a Cash- or Bank-type invoice.

    No-ops for Credit / empty payment type, already-settled invoices, and
    invoices that already have a submitted Payment Entry against them.
    """
    if invoice.doctype not in CASH_PAYMENT_DOCTYPES or invoice.docstatus != 1:
        return

    payment_type = (invoice.get("custom_payment_type") or "").strip()
    if payment_type not in AUTO_PAYMENT_TYPES:
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

    fieldname, field_label, account_type = AUTO_PAYMENT_TYPES[payment_type]
    account = invoice.get(fieldname)
    if not account:
        frappe.throw(
            f"Cannot submit {invoice.name}: Payment Type is {payment_type} but no "
            f"{field_label} was selected. Pick one in the {field_label} field "
            f"before submitting."
        )
    _validate_payment_account(account, invoice.company, field_label, account_type)

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    payment_entry = get_payment_entry(invoice.doctype, invoice.name, bank_account=account)
    if payment_type == "Cash":
        payment_entry.mode_of_payment = CASH_MODE_OF_PAYMENT
    else:
        payment_entry.mode_of_payment = _bank_mode_of_payment(account, invoice.company)
        payment_entry.reference_no = (invoice.get("custom_bank_reference_no") or "").strip() or invoice.name
        payment_entry.reference_date = invoice.posting_date
    # Part of the sale, not a VanSaleX "collection" (vansalex_access backstop).
    payment_entry.flags.zatgo_auto_cash_payment = True
    payment_entry.insert(ignore_permissions=True)
    payment_entry.submit()

    logger.info(
        "Auto-created Payment Entry %s (%s) for %s %s",
        payment_entry.name,
        payment_type,
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
        if not _pays_only(payment_entry, invoice):
            # Also pays other invoices or holds an unallocated advance (a
            # VanSaleX collection spread oldest-first, a bulk receipt):
            # cancelling it would reverse money really received and reopen
            # the other invoices. Left to ERPNext, whose on_cancel unlinks
            # this invoice from it (Accounts Settings "Unlink Payment on
            # Cancellation of Invoice") or refuses the cancel.
            logger.info(
                "Not auto-cancelling Payment Entry %s: it also settles other documents "
                "or holds an advance (cancelling %s %s)",
                pe_name,
                invoice.doctype,
                invoice.name,
            )
            continue
        payment_entry.flags.ignore_permissions = True
        payment_entry.cancel()
        logger.info(
            "Auto-cancelled Payment Entry %s (linked to cancelled %s %s)",
            pe_name,
            invoice.doctype,
            invoice.name,
        )


def _pays_only(payment_entry: Document, invoice: Document) -> bool:
    """Every reference row is [invoice] and nothing is left unallocated --
    the shape of the auto Cash / Bank payment (or a one-invoice payment)."""
    return all(
        r.reference_doctype == invoice.doctype and r.reference_name == invoice.name
        for r in payment_entry.references or []
    ) and frappe.utils.flt(payment_entry.unallocated_amount) <= 0


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


def _validate_payment_account(account: str, company: str, field_label: str, account_type: str) -> None:
    row = frappe.db.get_value(
        "Account", account, ["company", "account_type", "is_group"], as_dict=True
    )
    if not row:
        frappe.throw(f"{field_label} '{account}' does not exist.")
    if row.company != company:
        frappe.throw(
            f"{field_label} '{account}' belongs to company '{row.company}', not "
            f"'{company}'. Pick a {field_label} that belongs to this invoice's company."
        )
    if row.is_group:
        frappe.throw(
            f"{field_label} '{account}' is a group account and cannot receive "
            f"payments directly. Pick a specific ledger account."
        )
    if row.account_type != account_type:
        frappe.throw(
            f"{field_label} '{account}' is not a {account_type}-type account "
            f"(account_type={row.account_type!r}). Pick an account with "
            f"Account Type = {account_type}."
        )


def _bank_mode_of_payment(account: str, company: str) -> str | None:
    """The enabled Bank-type Mode of Payment whose default account for this
    company is `account` -- None (left blank, as ERPNext allows) unless
    exactly one matches."""
    names = frappe.get_all(
        "Mode of Payment Account",
        filters={"company": company, "default_account": account, "parenttype": "Mode of Payment"},
        pluck="parent",
        distinct=True,
    )
    names = [
        n for n in names
        if frappe.db.get_value("Mode of Payment", n, ["type", "enabled"]) == ("Bank", 1)
    ]
    return names[0] if len(names) == 1 else None
