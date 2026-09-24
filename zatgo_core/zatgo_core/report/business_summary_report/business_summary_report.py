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

Party Balance (Payable/Receivable) is a point-in-time balance as of
`to_date`, not a sum of range-local transactions -- summing only the
range's invoices would misrepresent what a party actually owes if they
have older unpaid invoices outside the selected window. It's the sum of
`outstanding_amount` (ERPNext's own maintained field, updated by ERPNext's
own payment/reconciliation logic) on submitted invoices posted on or
before `to_date`.
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

    sales_total, sales_count = get_invoice_summary("Sales Invoice", "grand_total", company, from_date, to_date)
    purchase_total, purchase_count = get_invoice_summary(
        "Purchase Invoice", "grand_total", company, from_date, to_date
    )
    payment_total, payment_count = get_payment_summary(company, from_date, to_date, "Pay", "paid_amount")
    receipt_total, receipt_count = get_payment_summary(company, from_date, to_date, "Receive", "received_amount")
    receivable, payable = get_party_balances(company, to_date)

    columns = get_columns()
    data = [
        {"transaction_type": _("Sales Invoice"), "count": sales_count, "total_amount": sales_total},
        {"transaction_type": _("Purchase Invoice"), "count": purchase_count, "total_amount": purchase_total},
        {"transaction_type": _("Party Payment"), "count": payment_count, "total_amount": payment_total},
        {"transaction_type": _("Party Receipt"), "count": receipt_count, "total_amount": receipt_total},
    ]

    currency = frappe.get_cached_value("Company", company, "default_currency")
    report_summary = [
        {"value": sales_total, "label": _("Sales Total"), "datatype": "Currency", "currency": currency},
        {"value": purchase_total, "label": _("Purchase Total"), "datatype": "Currency", "currency": currency},
        {"value": payment_total, "label": _("Party Payment Total"), "datatype": "Currency", "currency": currency},
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


def get_party_balances(company, to_date):
    receivable_row = frappe.db.sql(
        """
        select sum(outstanding_amount) as total
        from `tabSales Invoice`
        where docstatus = 1 and company = %(company)s and posting_date <= %(to_date)s
        """,
        {"company": company, "to_date": to_date},
        as_dict=True,
    )[0]
    payable_row = frappe.db.sql(
        """
        select sum(outstanding_amount) as total
        from `tabPurchase Invoice`
        where docstatus = 1 and company = %(company)s and posting_date <= %(to_date)s
        """,
        {"company": company, "to_date": to_date},
        as_dict=True,
    )[0]
    return flt(receivable_row.total), flt(payable_row.total)


def get_columns():
    return [
        {"fieldname": "transaction_type", "label": _("Transaction Type"), "fieldtype": "Data", "width": 220},
        {"fieldname": "count", "label": _("Count"), "fieldtype": "Int", "width": 100},
        {"fieldname": "total_amount", "label": _("Total Amount"), "fieldtype": "Currency", "width": 180},
    ]
