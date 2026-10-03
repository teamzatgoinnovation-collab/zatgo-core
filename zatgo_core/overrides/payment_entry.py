"""Payment Entry class extension (hooks.py `extend_doctype_class`).

Only the bank-side GL line changes: when `custom_payment_details` rows are
present, the single paid_to (Receive) / paid_from (Pay) line ERPNext would
post is replaced by one line per row, in the same direction, whose
company-currency amounts sum exactly to the amount ERPNext would have posted
(services/payment_allocation.split_base_amounts). Party line, references,
outstanding updates, deductions, taxes, exchange gain/loss and cancellation
(ERPNext reverses the posted GL rows) are all ERPNext's own code.

`extend_doctype_class` (not override_doctype_class) because hrms already
overrides the Payment Entry class; this mixes in on top of it.
"""

from __future__ import annotations

from frappe.utils import flt

from zatgo_core.services.payment_allocation import split_base_amounts


class ZatGoPaymentEntry:
    def add_bank_gl_entries(self, gl_entries):
        rows = [r for r in self.get("custom_payment_details") or [] if flt(r.amount)]
        if not rows or self.payment_type not in ("Receive", "Pay"):
            return super().add_bank_gl_entries(gl_entries)

        split_base_amounts(self)
        receive = self.payment_type == "Receive"
        account_currency = self.paid_to_account_currency if receive else self.paid_from_account_currency
        side = "debit" if receive else "credit"

        for row in rows:
            entry = {
                "account": row.account,
                "account_currency": account_currency,
                "against": self.party,
                f"{side}_in_account_currency": flt(row.amount),
                f"{side}_in_transaction_currency": flt(row.amount)
                if account_currency == self.transaction_currency
                else flt(row.base_amount) / self.transaction_exchange_rate,
                side: flt(row.base_amount),
                "cost_center": self.cost_center,
            }
            if not receive:
                entry["post_net_value"] = True
            if row.get("remarks"):
                entry["remarks"] = row.remarks
            gl_entries.append(self.get_gl_dict(entry, item=self))
