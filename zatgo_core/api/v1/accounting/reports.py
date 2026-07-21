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
