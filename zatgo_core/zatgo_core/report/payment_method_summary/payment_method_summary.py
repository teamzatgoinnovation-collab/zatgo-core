"""Money received / paid per Payment Method and per ledger account.

Answers "how much came in through Cash / HDFC POS / UPI?" across every place
ERPNext records which method + account money moved through, in company
currency, for submitted documents only:

1. Sales Invoice payment rows (`tabSales Invoice Payment`) on `is_pos`
   invoices -- paid on the invoice itself; posted by ERPNext's
   make_pos_gl_entries(). A return's (negative) refund rows count as paid out.
2. Payment Entry `custom_payment_details` rows (ZG Payment Allocation) --
   the split posted by zatgo_core.overrides.payment_entry.
3. Payment Entries *without* such rows -- ERPNext's own single account:
   paid_to on Receive, paid_from on Pay (header mode_of_payment).

The three are disjoint (a Payment Entry is in exactly one of 2/3; an invoice
paid via a separate Payment Entry has no payment rows), so nothing is
counted twice. Internal Transfers are not receipts or payments and are left
out. Read-only aggregates; the General Ledger stays the authority for
account balances.
"""

from __future__ import annotations

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not (filters.company and filters.from_date and filters.to_date):
        return get_columns(filters), []
    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("From Date cannot be after To Date."))

    rows = _invoice_payment_rows(filters) + _allocation_rows(filters) + _plain_payment_entry_rows(filters)
    return get_columns(filters), _group(rows, filters.group_by or "Payment Method and Account")


def get_columns(filters):
    group_by = filters.get("group_by") or "Payment Method and Account"
    columns = []
    if group_by != "Account":
        columns.append(
            {"fieldname": "mode_of_payment", "label": _("Payment Method"), "fieldtype": "Link",
             "options": "Mode of Payment", "width": 160}
        )
    if group_by != "Payment Method":
        columns.append(
            {"fieldname": "account", "label": _("Account"), "fieldtype": "Link", "options": "Account", "width": 220}
        )
    columns += [
        {"fieldname": "received", "label": _("Received"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "paid", "label": _("Paid"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "net", "label": _("Net"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "rows", "label": _("Payment Rows"), "fieldtype": "Int", "width": 110},
    ]
    return columns


def _conditions(filters, mop_col: str, account_col: str) -> tuple[str, dict]:
    sql = ""
    values = {"company": filters.company, "from_date": filters.from_date, "to_date": filters.to_date}
    if filters.mode_of_payment:
        sql += f" and {mop_col} = %(mode_of_payment)s"
        values["mode_of_payment"] = filters.mode_of_payment
    if filters.account:
        sql += f" and {account_col} = %(account)s"
        values["account"] = filters.account
    return sql, values


def _invoice_payment_rows(filters):
    cond, values = _conditions(filters, "sip.mode_of_payment", "sip.account")
    return frappe.db.sql(
        f"""
        select sip.mode_of_payment, sip.account,
            sum(case when sip.base_amount > 0 then sip.base_amount else 0 end) as received,
            sum(case when sip.base_amount < 0 then -sip.base_amount else 0 end) as paid,
            count(*) as row_count
        from `tabSales Invoice Payment` sip
        inner join `tabSales Invoice` si on si.name = sip.parent
        where sip.parenttype = 'Sales Invoice' and si.docstatus = 1 and si.is_pos = 1
            and sip.base_amount != 0
            and si.company = %(company)s and si.posting_date between %(from_date)s and %(to_date)s
            {cond}
        group by sip.mode_of_payment, sip.account
        """,
        values,
        as_dict=True,
    )


def _allocation_rows(filters):
    if not frappe.db.has_table("ZG Payment Allocation"):
        return []
    cond, values = _conditions(filters, "pa.mode_of_payment", "pa.account")
    return frappe.db.sql(
        f"""
        select pa.mode_of_payment, pa.account,
            sum(case when pe.payment_type = 'Receive' then pa.base_amount else 0 end) as received,
            sum(case when pe.payment_type = 'Pay' then pa.base_amount else 0 end) as paid,
            count(*) as row_count
        from `tabZG Payment Allocation` pa
        inner join `tabPayment Entry` pe on pe.name = pa.parent
        where pa.parenttype = 'Payment Entry' and pe.docstatus = 1
            and pe.payment_type in ('Receive', 'Pay')
            and pe.company = %(company)s and pe.posting_date between %(from_date)s and %(to_date)s
            {cond}
        group by pa.mode_of_payment, pa.account
        """,
        values,
        as_dict=True,
    )


def _plain_payment_entry_rows(filters):
    account_expr = "(case when pe.payment_type = 'Receive' then pe.paid_to else pe.paid_from end)"
    cond, values = _conditions(filters, "pe.mode_of_payment", account_expr)
    no_rows = (
        "and not exists (select 1 from `tabZG Payment Allocation` pa "
        "where pa.parent = pe.name and pa.parenttype = 'Payment Entry')"
        if frappe.db.has_table("ZG Payment Allocation")
        else ""
    )
    return frappe.db.sql(
        f"""
        select pe.mode_of_payment, {account_expr} as account,
            sum(case when pe.payment_type = 'Receive' then pe.base_received_amount else 0 end) as received,
            sum(case when pe.payment_type = 'Pay' then pe.base_paid_amount else 0 end) as paid,
            count(*) as row_count
        from `tabPayment Entry` pe
        where pe.docstatus = 1 and pe.payment_type in ('Receive', 'Pay')
            and pe.company = %(company)s and pe.posting_date between %(from_date)s and %(to_date)s
            {no_rows}
            {cond}
        group by pe.mode_of_payment, {account_expr}
        """,
        values,
        as_dict=True,
    )


def _group(rows, group_by: str):
    out: OrderedDict = OrderedDict()
    for r in rows:
        mop = r.mode_of_payment or _("(Not Set)")
        if group_by == "Payment Method":
            key = (mop,)
        elif group_by == "Account":
            key = (r.account,)
        else:
            key = (mop, r.account)
        agg = out.setdefault(
            key, {"mode_of_payment": mop, "account": r.account, "received": 0.0, "paid": 0.0, "rows": 0}
        )
        agg["received"] += flt(r.received)
        agg["paid"] += flt(r.paid)
        agg["rows"] += int(r.row_count or 0)
    data = []
    for agg in sorted(out.values(), key=lambda a: (str(a["mode_of_payment"]), str(a["account"]))):
        agg["net"] = flt(agg["received"] - agg["paid"])
        data.append(agg)
    return data
