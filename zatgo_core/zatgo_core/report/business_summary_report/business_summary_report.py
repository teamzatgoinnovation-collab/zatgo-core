"""Date-range business summary: sales, purchases, party payments/receipts,
and current payable/receivable balances.

Every card is a General Ledger figure (what the Trial Balance / Profit and Loss
/ Balance Sheet show), one server-side aggregate each:

* Sales Total -- Income accounts, net, for the range (same as the P&L).
* Purchases Total -- purchase invoices net of purchase returns, as posted to
  the Payable accounts in the range (tax included, stock and non-stock).
  So Purchases - Payable balance = Party Payment when the range starts at
  zero. Cost of Goods Sold (what was actually sold) is its own row; stock
  bought but not yet sold is the difference.
* Party Payment -- money paid out through the Payable accounts in the range:
  Payment Entries and Journal Entries, net of refunds back to us.
* Party Receipt -- money received through the Receivable accounts in the
  range: Payment Entries and Journal Entries, net of refunds to customers.
  Receipts = sales - receivable balance when a customer started at zero.
* Party Balance (Payable / Receivable) -- closing balance as of `to_date`.
  A negative balance means the party owes the other way.
* Total Expense / Net Profit rows -- P&L, period-closing entries excluded.

Invoice documents are only used for the Sales Invoice count (returns count as
one each).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
    filters = frappe._dict(filters or {})
    company = filters.company or frappe.defaults.get_user_default("Company")
    from_date = filters.from_date
    to_date = filters.to_date

    if not (company and from_date and to_date):
        return get_columns(), [], None, None, []

    validate_filters(company, from_date, to_date)

    sales_count = get_sales_invoice_count(company, from_date, to_date)
    pnl = get_profit_and_loss(company, from_date, to_date)
    sales_total = pnl["income"]
    purchase_total = get_purchases_total(company, from_date, to_date)
    payments = get_party_cash_movement(company, from_date, to_date, "Payable")
    receipts = get_party_cash_movement(company, from_date, to_date, "Receivable")
    receivable = get_ledger_balance(company, to_date, "Receivable")
    payable = 0.0 - get_ledger_balance(company, to_date, "Payable")  # 0.0 - x: never "-0.00"

    data = [
        {"transaction_type": _("Sales"), "count": sales_count, "total_amount": sales_total},
        {"transaction_type": _("Purchases"), "count": None, "total_amount": purchase_total},
        {"transaction_type": _("Party Payment"), "count": None, "total_amount": payments},
        {"transaction_type": _("Party Receipt"), "count": None, "total_amount": receipts},
        {"transaction_type": _("Cost of Goods Sold (ledger)"), "count": None, "total_amount": pnl["cogs"]},
        {"transaction_type": _("Total Expense (ledger)"), "count": None, "total_amount": pnl["expense"]},
        {"transaction_type": _("Net Profit (ledger)"), "count": None, "total_amount": pnl["income"] - pnl["expense"]},
    ]

    currency = frappe.get_cached_value("Company", company, "default_currency")

    def card(label, value, indicator=None):
        c = {"value": value, "label": label, "datatype": "Currency", "currency": currency}
        if indicator:
            c["indicator"] = indicator if value else "Grey"
        return c

    report_summary = [
        card(_("Sales Total"), sales_total),
        card(_("Purchases Total"), purchase_total),
        card(_("Party Payment Total"), payments),
        card(_("Party Receipt Total"), receipts),
        card(_("Party Balance - Payable"), payable, "Red"),
        card(_("Party Balance - Receivable"), receivable, "Green"),
    ]

    return get_columns(), data, None, None, report_summary


def validate_filters(company, from_date, to_date) -> None:
    # The raw SQL below skips Company User Permissions, so enforce them here.
    frappe.has_permission("Company", "read", doc=company, throw=True)
    if getdate(from_date) > getdate(to_date):
        frappe.throw(_("From Date cannot be greater than To Date"))


def get_sales_invoice_count(company, from_date, to_date):
    return frappe.db.count(
        "Sales Invoice",
        {"docstatus": 1, "company": company, "posting_date": ["between", [from_date, to_date]]},
    )


def get_purchases_total(company, from_date, to_date):
    """Purchase invoices net of purchase returns: what the Payable accounts
    were credited (debited for returns) by Purchase Invoices in the range."""
    row = frappe.db.sql(
        """
        select sum(g.credit - g.debit) as net
        from `tabGL Entry` g join `tabAccount` a on a.name = g.account
        where g.company = %(company)s and g.is_cancelled = 0
          and a.account_type = 'Payable' and a.root_type = 'Liability'
          and g.voucher_type = 'Purchase Invoice'
          and g.posting_date between %(from_date)s and %(to_date)s
        """,
        {"company": company, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )[0]
    return flt(row.net)


def get_party_cash_movement(company, from_date, to_date, account_type):
    """Cash moved through the company's Payable (paid out) or Receivable
    (received) accounts in the range, from Payment and Journal Entries, net of
    refunds the other way. Invoices and credit/debit notes are not cash."""
    root_type = "Asset" if account_type == "Receivable" else "Liability"
    row = frappe.db.sql(
        """
        select sum(g.debit - g.credit) as net
        from `tabGL Entry` g join `tabAccount` a on a.name = g.account
        where g.company = %(company)s and g.is_cancelled = 0
          and a.account_type = %(account_type)s and a.root_type = %(root_type)s
          and g.voucher_type in ('Payment Entry', 'Journal Entry')
          and g.posting_date between %(from_date)s and %(to_date)s
        """,
        {"company": company, "account_type": account_type, "root_type": root_type,
         "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )[0]
    # Payable: paying = debit (positive). Receivable: receiving = credit.
    return flt(row.net) if account_type == "Payable" else 0.0 - flt(row.net)


def get_ledger_balance(company, to_date, account_type):
    """Debit-minus-credit balance of the company's `account_type` accounts as
    of `to_date` (Receivable: positive = customers owe us; Payable: negate)."""
    root_type = "Asset" if account_type == "Receivable" else "Liability"
    row = frappe.db.sql(
        """
        select sum(g.debit - g.credit) as bal
        from `tabGL Entry` g join `tabAccount` a on a.name = g.account
        where g.company = %(company)s and g.is_cancelled = 0
          and a.account_type = %(account_type)s and a.root_type = %(root_type)s
          and g.posting_date <= %(to_date)s
        """,
        {"company": company, "account_type": account_type, "root_type": root_type, "to_date": to_date},
        as_dict=True,
    )[0]
    return flt(row.bal)


def get_profit_and_loss(company, from_date, to_date):
    """Income / expense / COGS from the General Ledger, as the Profit and Loss
    Statement computes them (period-closing entries excluded)."""
    rows = frappe.db.sql(
        """
        select a.root_type, a.account_type, sum(g.credit - g.debit) as net
        from `tabGL Entry` g join `tabAccount` a on a.name = g.account
        where g.company = %(company)s and g.is_cancelled = 0
          and g.voucher_type != 'Period Closing Voucher'
          and g.posting_date between %(from_date)s and %(to_date)s
          and a.root_type in ('Income', 'Expense')
        group by a.root_type, a.account_type
        """,
        {"company": company, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )
    out = {"income": 0.0, "expense": 0.0, "cogs": 0.0}
    for r in rows:
        if r.root_type == "Income":
            out["income"] += flt(r.net)
        else:
            out["expense"] -= flt(r.net)
            if r.account_type == "Cost of Goods Sold":
                out["cogs"] -= flt(r.net)
    return out


def get_columns():
    return [
        {"fieldname": "transaction_type", "label": _("Transaction Type"), "fieldtype": "Data", "width": 220},
        {"fieldname": "count", "label": _("Count"), "fieldtype": "Int", "width": 100},
        {"fieldname": "total_amount", "label": _("Total Amount"), "fieldtype": "Currency", "width": 180},
    ]
