"""Date-range business summary: sales, purchases, party payments/receipts,
and current payable/receivable balances.

Every figure is a single server-side aggregate (SUM/COUNT) against ERPNext's
own standard fields -- no per-row fetching, no duplicate accounting logic.
Sales/Purchase totals sum `grand_total` across ALL submitted invoices in the
range, which nets out returns and debit/credit notes for free: ERPNext
already stores a return document's amounts as negative (`is_return=1`
flips the sign at submit time), so a plain SUM already reflects net sales/
net purchases exactly as ERPNext's own reports do -- no extra "exclude
returns" branch needed or wanted.

"Purchases Total" is the cost of the goods actually sold (ledger Cost of
Goods Sold, same figure as the Profit and Loss Statement): stock bought but
not yet sold is an asset and not part of it. Income / expense / net profit
rows also come from the ledger and tie to the P&L.

Party Payment is the part of outgoing Payment Entries allocated to invoices;
the unallocated part (advances) is its own card.

Party Balance (Payable/Receivable) is a point-in-time balance as of
`to_date`, read from the General Ledger Receivable/Payable accounts (same as
the Balance Sheet), so advances, journals and returns are netted. A negative
payable / receivable means the party owes the other way.
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

    validate_filters(from_date, to_date)

    # base_grand_total = company currency, so a foreign-currency invoice is
    # not summed at its transaction-currency face value.
    sales_total, sales_count = get_invoice_summary("Sales Invoice", "base_grand_total", company, from_date, to_date)
    gl = get_gl_result(company, from_date, to_date)
    purchase_total = gl["cogs"]
    payment_total, payment_count, advance_total = get_supplier_payments(company, from_date, to_date)
    receipt_total, receipt_count = get_payment_summary(company, from_date, to_date, "Receive", "received_amount")
    receivable, payable = get_party_balances(company, to_date)

    columns = get_columns()
    data = [
        {"transaction_type": _("Sales Invoice"), "count": sales_count, "total_amount": sales_total},
        {"transaction_type": _("Purchases"), "count": None, "total_amount": purchase_total},
        {"transaction_type": _("Party Payment"), "count": payment_count, "total_amount": payment_total},
        {"transaction_type": _("Advance / Unallocated Payment"), "count": None, "total_amount": advance_total},
        {"transaction_type": _("Party Receipt"), "count": receipt_count, "total_amount": receipt_total},
        # Ledger view -- the same figures as the Profit and Loss Statement.
        {"transaction_type": _("Income (ledger)"), "count": None, "total_amount": gl["income"]},
        {"transaction_type": _("Total Expense (ledger)"), "count": None, "total_amount": gl["expense"]},
        {"transaction_type": _("Net Profit (ledger)"), "count": None, "total_amount": gl["income"] - gl["expense"]},
    ]

    currency = frappe.get_cached_value("Company", company, "default_currency")
    report_summary = [
        {"value": sales_total, "label": _("Sales Total"), "datatype": "Currency", "currency": currency},
        {"value": purchase_total, "label": _("Purchases Total"), "datatype": "Currency", "currency": currency},
        {"value": payment_total, "label": _("Party Payment Total"), "datatype": "Currency", "currency": currency},
        {
            "value": advance_total,
            "label": _("Advance / Unallocated"),
            "datatype": "Currency",
            "currency": currency,
        },
        {"value": receipt_total, "label": _("Party Receipt Total"), "datatype": "Currency", "currency": currency},
        {
            "value": payable,
            "label": _("Party Balance - Payable"),
            "datatype": "Currency",
            "currency": currency,
            "indicator": "Red" if payable else "Grey",
        },
        {
            "value": receivable,
            "label": _("Party Balance - Receivable"),
            "datatype": "Currency",
            "currency": currency,
            "indicator": "Green" if receivable else "Grey",
        },
    ]

    return columns, data, None, None, report_summary


def validate_filters(from_date, to_date) -> None:
    if getdate(from_date) > getdate(to_date):
        frappe.throw(_("From Date cannot be greater than To Date"))


def get_invoice_summary(doctype, amount_field, company, from_date, to_date):
    # frappe.get_all() rejects raw SQL function strings in `fields` (Frappe
    # v16 hardening) -- accounting.md sanctions frappe.db.sql for read-only
    # aggregates like this. amount_field is always one of our own fixed
    # column-name constants below, never filter input, so the f-string is
    # safe; company/dates are bound parameters.
    row = frappe.db.sql(
        f"""
        select sum({amount_field}) as total, count(name) as cnt
        from `tab{doctype}`
        where docstatus = 1 and company = %(company)s
          and posting_date between %(from_date)s and %(to_date)s
        """,
        {"company": company, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )[0]
    return flt(row.total), int(row.cnt or 0)


def get_payment_summary(company, from_date, to_date, payment_type, amount_field):
    row = frappe.db.sql(
        f"""
        select sum({amount_field}) as total, count(name) as cnt
        from `tabPayment Entry`
        where docstatus = 1 and company = %(company)s and payment_type = %(payment_type)s
          and posting_date between %(from_date)s and %(to_date)s
        """,
        {"company": company, "payment_type": payment_type, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )[0]
    return flt(row.total), int(row.cnt or 0)


def get_gl_result(company, from_date, to_date):
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


def get_supplier_payments(company, from_date, to_date):
    """Outgoing Payment Entries split into the part allocated to invoices and
    the unallocated (advance) part, in company currency."""
    row = frappe.db.sql(
        """
        select count(name) as cnt,
               sum(base_paid_amount) as total,
               sum(unallocated_amount * source_exchange_rate) as advance
        from `tabPayment Entry`
        where docstatus = 1 and company = %(company)s and payment_type = 'Pay'
          and posting_date between %(from_date)s and %(to_date)s
        """,
        {"company": company, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )[0]
    advance = flt(row.advance)
    return flt(row.total) - advance, int(row.cnt or 0), advance


def get_party_balances(company, to_date):
    """Receivable / payable as of `to_date` from the General Ledger (the same
    figures as the Balance Sheet): unlike summing invoice outstanding, this
    nets unallocated payments/receipts, journal entries and returns."""
    rows = frappe.db.sql(
        """
        select a.account_type, sum(g.debit - g.credit) as bal
        from `tabGL Entry` g join `tabAccount` a on a.name = g.account
        where g.company = %(company)s and g.is_cancelled = 0
          and a.account_type in ('Receivable', 'Payable') and g.posting_date <= %(to_date)s
        group by a.account_type
        """,
        {"company": company, "to_date": to_date},
        as_dict=True,
    )
    bal = {r.account_type: flt(r.bal) for r in rows}
    return bal.get("Receivable", 0.0), -bal.get("Payable", 0.0)


def get_columns():
    return [
        {"fieldname": "transaction_type", "label": _("Transaction Type"), "fieldtype": "Data", "width": 220},
        {"fieldname": "count", "label": _("Count"), "fieldtype": "Int", "width": 100},
        {"fieldname": "total_amount", "label": _("Total Amount"), "fieldtype": "Currency", "width": 180},
    ]
