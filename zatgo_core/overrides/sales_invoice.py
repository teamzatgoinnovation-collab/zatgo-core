"""Sales Invoice class extension (hooks.py `extend_doctype_class`).

ERPNext's before_save calls set_account_for_mode_of_payment(), which
unconditionally replaces every payment row's account with the Mode of
Payment's single per-company default -- so a row deliberately posted to
"Petty Cash" would silently be booked to "Cash" instead. This keeps a row's
account when it is one of that mode's allowed accounts
(services/payment_allocation.allowed_accounts) and otherwise does exactly
what ERPNext did. GL posting itself is untouched: ERPNext's
make_pos_gl_entries() posts each row.
"""

from __future__ import annotations

import frappe

from zatgo_core.services.payment_allocation import default_account, is_allowed_account


class ZatGoSalesInvoice:
    # Whitelisted like ERPNext's original: the Sales Invoice form calls it
    # (frm.call) whenever a payment row's Mode of Payment changes.
    @frappe.whitelist()
    def set_account_for_mode_of_payment(self):
        from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

        for payment in self.payments:
            if not payment.mode_of_payment:
                continue
            if payment.account and is_allowed_account(payment.account, payment.mode_of_payment, self.company):
                continue
            payment.account = (
                default_account(payment.mode_of_payment, self.company)
                or get_bank_cash_account(payment.mode_of_payment, self.company).get("account")
            )
