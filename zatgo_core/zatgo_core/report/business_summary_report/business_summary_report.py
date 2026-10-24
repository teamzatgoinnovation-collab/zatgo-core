"""Date-range business summary: sales, purchases, party payments/receipts,
and current payable/receivable balances.

Where each figure comes from (one server-side aggregate each, against ERPNext's
own documents and ledger -- no duplicate accounting logic):

* Sales Total -- `base_grand_total` of submitted Sales Invoices in the range
  (company currency, tax included). Returns are stored negative by ERPNext,
  so a plain SUM is already net of credit notes.
* Purchases Total -- Cost of Goods Sold from the General Ledger (same figure
  as the Profit and Loss Statement). Stock bought but not yet sold is an
  asset, not a purchase expense.
* Party Payment / Party Receipt -- Payment Entries to Suppliers / from
  Customers, split into the part allocated to invoices and the unallocated
  part (advances). A refund the other way (a supplier refunding us, us
  refunding a customer) is netted off. Internal transfers and other party
  types (employee, shareholder) are not party payments/receipts.
* Party Balance (Payable / Receivable) -- point in time as of `to_date`,
  read from the General Ledger Payable / Receivable accounts (same as the
  Balance Sheet), so advances, journal entries and returns are netted. Summing
  invoice `outstanding_amount` instead misses anything settled by journal or
  left unallocated. A negative balance means the party owes the other way.
* Income / Expense / Net Profit rows -- General Ledger, period-closing
  entries excluded, tying to the Profit and Loss Statement.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate

# party_type -> payment_type that is the "main" flow; the other one is a refund
MAIN_FLOW = {"Supplier": "Pay", "Customer": "Receive"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    company = filters.company or frappe.defaults.get_user_default("Company")
    from_date = filters.from_date
    to_date = filters.to_date

    if not (company and from_date and to_date):
        return get_columns(), [], None, None, []

    validate_filters(company, from_date, to_date)

    sales_total, sales_count = get_sales_summary(company, from_date, to_date)
    pnl = get_profit_and_loss(company, from_date, to_date)
    purchase_total = pnl["cogs"]
    payments = get_party_payments(company, from_date, to_date, "Supplier")
    receipts = get_party_payments(company, from_date, to_date, "Customer")
    receivable = get_ledger_balance(company, to_date, "Receivable")
    payable = 0.0 - get_ledger_balance(company, to_date, "Payable")  # 0.0 - x: never "-0.00"

    data = [
        {"transaction_type": _("Sales Invoice"), "count": sales_count, "total_amount": sales_total},
        {"transaction_type": _("Purchases"), "count": None, "total_amount": purchase_total},
        {"transaction_type": _("Party Payment"), "count": payments.count, "total_amount": payments.allocated},
        {"transaction_type": _("Advance Payment (Unallocated)"), "count": None, "total_amount": payments.advance},
        {"transaction_type": _("Party Receipt"), "count": receipts.count, "total_amount": receipts.allocated},
        {"transaction_type": _("Advance Receipt (Unallocated)"), "count": None, "total_amount": receipts.advance},
        {"transaction_type": _("Income (ledger)"), "count": None, "total_amount": pnl["income"]},
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
        card(_("Party Payment Total"), payments.allocated),
        card(_("Advance Payment (Unallocated)"), payments.advance),
        card(_("Party Receipt Total"), receipts.allocated),
        card(_("Advance Receipt (Unallocated)"), receipts.advance),
        card(_("Party Balance - Payable"), payable, "Red"),
        card(_("Party Balance - Receivable"), receivable, "Green"),
    ]

    return get_columns(), data, None, None, report_summary


def validate_filters(company, from_date, to_date) -> None:
    # The raw SQL below skips Company User Permissions, so enforce them here.
    frappe.has_permission("Company", "read", doc=company, throw=True)
    if getdate(from_date) > getdate(to_date):
        frappe.throw(_("From Date cannot be greater than To Date"))


def get_sales_summary(company, from_date, to_date):
    # frappe.get_all() rejects raw SQL function strings in `fields` (Frappe
    # v16 hardening) -- accounting.md sanctions frappe.db.sql for read-only
    # aggregates like this. Company/dates are bound parameters.
    row = frappe.db.sql(
        """
        select sum(base_grand_total) as total, count(name) as cnt
        from `tabSales Invoice`
        where docstatus = 1 and company = %(company)s
          and posting_date between %(from_date)s and %(to_date)s
        """,
        {"company": company, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )[0]
    return flt(row.total), int(row.cnt or 0)


def get_party_payments(company, from_date, to_date, party_type):
    """Payments (Suppliers) or receipts (Customers) in company currency.

    Returns `allocated` (settled against invoices), `advance` (unallocated
    part) and `count` of main-flow entries. Refund entries (the opposite
    payment type for the same party type) are subtracted from both amounts.
    """
    main_type = MAIN_FLOW[party_type]
    rows = frappe.db.sql(
        """
        select payment_type,
               count(name) as cnt,
               sum(amount) as total,
               sum(amount * advance_share) as advance
        from (
            select name, payment_type,
                   if(payment_type = 'Pay', base_paid_amount, base_received_amount) as amount,
                   if(unallocated_amount + total_allocated_amount = 0, 0,
                      unallocated_amount / (unallocated_amount + total_allocated_amount)) as advance_share
            from `tabPayment Entry`
            where docstatus = 1 and company = %(company)s and party_type = %(party_type)s
              and payment_type in ('Pay', 'Receive')
              and posting_date between %(from_date)s and %(to_date)s
        ) pe
        group by payment_type
        """,
        {"company": company, "party_type": party_type, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )
    out = frappe._dict(allocated=0.0, advance=0.0, count=0)
    for r in rows:
        sign = 1 if r.payment_type == main_type else -1
        advance = flt(r.advance)
        out.allocated += sign * (flt(r.total) - advance)
        out.advance += sign * advance
        if sign == 1:
            out.count = int(r.cnt or 0)
    return out


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
