"""Accounting reports — outstanding, GL, P&L (db aggregates, not Desk query_report)."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, getdate, today

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login


def _date_range(from_date: str | None, to_date: str | None) -> tuple[Any, Any]:
    end = getdate(to_date) if to_date else getdate(today())
    start = getdate(from_date) if from_date else getdate(f"{end.year}-01-01")
    return start, end


@frappe.whitelist()
def outstanding_receivable(page: int | str = 1, page_size: int | str = 50) -> dict[str, Any]:
    require_login()
    rows = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0]},
        fields=[
            "name",
            "customer",
            "customer_name",
            "posting_date",
            "due_date",
            "grand_total",
            "outstanding_amount",
            "currency",
        ],
        order_by="due_date asc",
        limit_page_length=min(int(page_size or 50), 100),
        limit_start=(max(int(page or 1), 1) - 1) * min(int(page_size or 50), 100),
    )
    total = frappe.db.count("Sales Invoice", {"docstatus": 1, "outstanding_amount": [">", 0]})
    data = [
        {
            "id": r.name,
            "name": r.name,
            "party": r.customer_name or r.customer,
            "party_id": r.customer,
            "date": str(r.posting_date) if r.posting_date else None,
            "due_date": str(r.due_date) if r.due_date else None,
            "amount": flt(r.grand_total),
            "outstanding": flt(r.outstanding_amount),
            "currency": r.currency,
        }
        for r in rows
    ]
    return ok(
        data,
        meta={
            "stub": False,
            "total": total,
            "sum_outstanding": sum(d["outstanding"] for d in data),
            "source": "Sales Invoice",
        },
    )


@frappe.whitelist()
def outstanding_payable(page: int | str = 1, page_size: int | str = 50) -> dict[str, Any]:
    require_login()
    rows = frappe.get_all(
        "Purchase Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0]},
        fields=[
            "name",
            "supplier",
            "supplier_name",
            "posting_date",
            "due_date",
            "grand_total",
            "outstanding_amount",
            "currency",
        ],
        order_by="due_date asc",
        limit_page_length=min(int(page_size or 50), 100),
        limit_start=(max(int(page or 1), 1) - 1) * min(int(page_size or 50), 100),
    )
    total = frappe.db.count("Purchase Invoice", {"docstatus": 1, "outstanding_amount": [">", 0]})
    data = [
        {
            "id": r.name,
            "name": r.name,
            "party": r.supplier_name or r.supplier,
            "party_id": r.supplier,
            "date": str(r.posting_date) if r.posting_date else None,
            "due_date": str(r.due_date) if r.due_date else None,
            "amount": flt(r.grand_total),
            "outstanding": flt(r.outstanding_amount),
            "currency": r.currency,
        }
        for r in rows
    ]
    return ok(
        data,
        meta={
            "stub": False,
            "total": total,
            "sum_outstanding": sum(d["outstanding"] for d in data),
            "source": "Purchase Invoice",
        },
    )


@frappe.whitelist()
def general_ledger(
    from_date: str | None = None,
    to_date: str | None = None,
    account: str | None = None,
    voucher_type: str | None = None,
    page: int | str = 1,
    page_size: int | str = 100,
) -> dict[str, Any]:
    require_login()
    start, end = _date_range(from_date, to_date)
    filters: dict[str, Any] = {
        "posting_date": ["between", [start, end]],
        "is_cancelled": 0,
    }
    if account:
        filters["account"] = account
    if voucher_type:
        filters["voucher_type"] = voucher_type

    size = min(max(int(page_size or 100), 1), 200)
    page_i = max(int(page or 1), 1)
    total = frappe.db.count("GL Entry", filters)
    rows = frappe.get_all(
        "GL Entry",
        filters=filters,
        fields=[
            "name",
            "posting_date",
            "account",
            "debit",
            "credit",
            "voucher_type",
            "voucher_no",
            "party_type",
            "party",
            "remarks",
        ],
        order_by="posting_date asc, creation asc",
        start=(page_i - 1) * size,
        page_length=size,
    )
    data = [
        {
            "id": r.name,
            "date": str(r.posting_date) if r.posting_date else None,
            "account": r.account,
            "debit": flt(r.debit),
            "credit": flt(r.credit),
            "voucher_type": r.voucher_type,
            "voucher_no": r.voucher_no,
            "party": r.party,
            "party_type": r.party_type,
            "remarks": r.remarks,
        }
        for r in rows
    ]
    return ok(
        data,
        meta={
            "stub": False,
            "from_date": str(start),
            "to_date": str(end),
            "page": page_i,
            "page_size": size,
            "total": total,
            "source": "GL Entry",
        },
    )


@frappe.whitelist()
def party_ledger(
    party_type: str,
    party: str,
    from_date: str | None = None,
    to_date: str | None = None,
    page: int | str = 1,
    page_size: int | str = 100,
) -> dict[str, Any]:
    """GL Entry history for one Customer/Supplier, with a running balance."""
    require_login()
    if party_type not in ("Customer", "Supplier"):
        frappe.throw("party_type must be Customer or Supplier")
    if not party:
        frappe.throw("party is required")
    start, end = _date_range(from_date, to_date)
    filters: dict[str, Any] = {
        "posting_date": ["between", [start, end]],
        "is_cancelled": 0,
        "party_type": party_type,
        "party": party,
    }

    size = min(max(int(page_size or 100), 1), 200)
    page_i = max(int(page or 1), 1)

    opening_balance = flt(
        frappe.db.sql(
            "SELECT COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0) FROM `tabGL Entry` "
            "WHERE party_type=%s AND party=%s AND posting_date < %s AND is_cancelled=0",
            (party_type, party, start),
        )[0][0]
    )

    # Fetch the whole in-range window (bounded by page_size cap x a sane max) so the running
    # balance is correct for any page — a party ledger is not expected to have huge row counts.
    all_rows = frappe.get_all(
        "GL Entry",
        filters=filters,
        fields=["name", "posting_date", "account", "debit", "credit", "voucher_type", "voucher_no", "remarks"],
        order_by="posting_date asc, creation asc",
        limit_page_length=0,
    )
    total = len(all_rows)

    running = opening_balance
    ledger: list[dict[str, Any]] = []
    for r in all_rows:
        running += flt(r.debit) - flt(r.credit)
        ledger.append(
            {
                "id": r.name,
                "date": str(r.posting_date) if r.posting_date else None,
                "account": r.account,
                "debit": flt(r.debit),
                "credit": flt(r.credit),
                "voucher_type": r.voucher_type,
                "voucher_no": r.voucher_no,
                "remarks": r.remarks,
                "balance": flt(running),
            }
        )
    closing_balance = flt(running)
    start_idx = (page_i - 1) * size
    data = ledger[start_idx : start_idx + size]

    return ok(
        data,
        meta={
            "stub": False,
            "from_date": str(start),
            "to_date": str(end),
            "page": page_i,
            "page_size": size,
            "total": total,
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "source": "GL Entry",
        },
    )


@frappe.whitelist()
def trial_balance(from_date: str | None = None, to_date: str | None = None, company: str | None = None) -> dict[str, Any]:
    """Opening/period/closing debit+credit per account — raw sums from GL Entry,
    never netted or computed outside ERPNext's own ledger."""
    require_login()
    start, end = _date_range(from_date, to_date)
    company_filter = "AND acc.company = %(company)s" if company else ""
    params: dict[str, Any] = {"start": start, "end": end}
    if company:
        params["company"] = company

    opening_rows = frappe.db.sql(
        f"""
        select gle.account, sum(gle.debit) as debit, sum(gle.credit) as credit
        from `tabGL Entry` gle
        inner join `tabAccount` acc on acc.name = gle.account
        where gle.posting_date < %(start)s and ifnull(gle.is_cancelled, 0) = 0 {company_filter}
        group by gle.account
        """,
        params,
        as_dict=True,
    )
    period_rows = frappe.db.sql(
        f"""
        select gle.account, acc.account_name, acc.root_type, sum(gle.debit) as debit, sum(gle.credit) as credit
        from `tabGL Entry` gle
        inner join `tabAccount` acc on acc.name = gle.account
        where gle.posting_date between %(start)s and %(end)s and ifnull(gle.is_cancelled, 0) = 0 {company_filter}
        group by gle.account, acc.account_name, acc.root_type
        """,
        params,
        as_dict=True,
    )

    opening_by_account = {r.account: (flt(r.debit), flt(r.credit)) for r in opening_rows}
    # Accounts with only opening activity (no movement this period) still need a row.
    accounts_seen = {r.account for r in period_rows}
    missing = [a for a in opening_by_account if a not in accounts_seen]
    if missing:
        extra = frappe.get_all("Account", filters={"name": ["in", missing]}, fields=["name", "account_name", "root_type"])
        period_rows = period_rows + [
            frappe._dict(account=e.name, account_name=e.account_name, root_type=e.root_type, debit=0, credit=0)
            for e in extra
        ]

    data = []
    total_opening_debit = total_opening_credit = 0.0
    total_debit = total_credit = 0.0
    total_closing_debit = total_closing_credit = 0.0
    for r in sorted(period_rows, key=lambda x: x.account):
        opening_debit, opening_credit = opening_by_account.get(r.account, (0.0, 0.0))
        period_debit, period_credit = flt(r.debit), flt(r.credit)
        closing = (opening_debit - opening_credit) + (period_debit - period_credit)
        closing_debit = closing if closing > 0 else 0.0
        closing_credit = -closing if closing < 0 else 0.0
        if not (opening_debit or opening_credit or period_debit or period_credit):
            continue
        data.append(
            {
                "account": r.account,
                "account_name": r.account_name,
                "root_type": r.root_type,
                "opening_debit": opening_debit,
                "opening_credit": opening_credit,
                "debit": period_debit,
                "credit": period_credit,
                "closing_debit": closing_debit,
                "closing_credit": closing_credit,
            }
        )
        total_opening_debit += opening_debit
        total_opening_credit += opening_credit
        total_debit += period_debit
        total_credit += period_credit
        total_closing_debit += closing_debit
        total_closing_credit += closing_credit

    return ok(
        data,
        meta={
            "stub": False,
            "from_date": str(start),
            "to_date": str(end),
            "total_opening_debit": total_opening_debit,
            "total_opening_credit": total_opening_credit,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "total_closing_debit": total_closing_debit,
            "total_closing_credit": total_closing_credit,
            "source": "GL Entry",
        },
    )


@frappe.whitelist()
def profit_and_loss(from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
    require_login()
    start, end = _date_range(from_date, to_date)
    rows = frappe.db.sql(
        """
        select
            gle.account,
            acc.account_name,
            acc.root_type,
            sum(gle.debit) as debit,
            sum(gle.credit) as credit
        from `tabGL Entry` gle
        inner join `tabAccount` acc on acc.name = gle.account
        where gle.posting_date between %s and %s
          and ifnull(gle.is_cancelled, 0) = 0
          and acc.root_type in ('Income', 'Expense')
        group by gle.account, acc.account_name, acc.root_type
        order by acc.root_type, gle.account
        """,
        (start, end),
        as_dict=True,
    )

    income: list[dict[str, Any]] = []
    expense: list[dict[str, Any]] = []
    income_total = 0.0
    expense_total = 0.0
    for r in rows:
        # Income: credit - debit; Expense: debit - credit
        if r.root_type == "Income":
            amount = flt(r.credit) - flt(r.debit)
            income_total += amount
            income.append(
                {
                    "account": r.account,
                    "account_name": r.account_name,
                    "amount": amount,
                }
            )
        else:
            amount = flt(r.debit) - flt(r.credit)
            expense_total += amount
            expense.append(
                {
                    "account": r.account,
                    "account_name": r.account_name,
                    "amount": amount,
                }
            )

    return ok(
        {
            "from_date": str(start),
            "to_date": str(end),
            "income": income,
            "expense": expense,
            "income_total": income_total,
            "expense_total": expense_total,
            "net_profit": income_total - expense_total,
        },
        meta={"stub": False, "source": "GL Entry"},
    )
