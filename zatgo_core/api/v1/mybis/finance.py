"""MyBis -- Finance screen: headline ledger figures and trends, ERPNext's statements and receivable / payable aging with drill-down."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.v1.mybis import _common
from zatgo_core.api.validators import require_login, require_str
from zatgo_core.services.mybis import cache, finance, queries, scope

_PERIOD = ("company", "preset", "from_date", "to_date", "compare")


def _args(company, preset, from_date, to_date, compare, **extra) -> dict[str, Any]:
    return {"company": company, "preset": preset, "from_date": from_date, "to_date": to_date, "compare": compare, **extra}


def _kind(kind: str) -> str:
    if kind not in ("receivable", "payable"):
        frappe.throw(frappe._("kind must be receivable or payable"), frappe.ValidationError)
    return kind


@frappe.whitelist(methods=["GET", "POST"])
def summary(company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, compare: Any = 1, refresh: Any = 0) -> dict[str, Any]:
    """Revenue, COGS, gross / net profit, expenses (General Ledger) and cash, bank, receivables, payables as of the period's end."""
    return _common.run("finance_kpis", _args(company, preset, from_date, to_date, compare), ("gl",), finance.kpis, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def trends(company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, months: int | str = 12, refresh: Any = 0) -> dict[str, Any]:
    """Monthly revenue / expenses / profit and month-end receivables, payables and cash + bank for the months up to the period's end."""
    return _common.run("finance_trends", _args(company, preset, from_date, to_date, 0, months=months), ("gl",), lambda s: finance.trends(s, int(months)), refresh)


@frappe.whitelist(methods=["GET", "POST"])
def profit_and_loss(company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, compare: Any = 1, refresh: Any = 0) -> dict[str, Any]:
    """ERPNext's Profit and Loss Statement for the period (and the previous one)."""
    return _common.run("finance_pnl", _args(company, preset, from_date, to_date, compare), ("gl",), finance.profit_and_loss, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def balance_sheet(company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, compare: Any = 1, refresh: Any = 0) -> dict[str, Any]:
    """ERPNext's Balance Sheet as of the period's end (and of the previous period's end)."""
    return _common.run("finance_bs", _args(company, preset, from_date, to_date, compare), ("gl",), finance.balance_sheet, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def cash_flow(company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, compare: Any = 1, refresh: Any = 0) -> dict[str, Any]:
    """ERPNext's Cash Flow statement for the period (and the previous one)."""
    return _common.run("finance_cf", _args(company, preset, from_date, to_date, compare), ("gl",), finance.cash_flow, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def aging(kind: str = "receivable", company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None, refresh: Any = 0) -> dict[str, Any]:
    """Receivable / payable aging as of the period's end: totals per bucket and parties, most overdue first (ERPNext's summary report)."""
    k = _kind(kind)
    return _common.run("finance_aging", _args(company, preset, from_date, to_date, 0, kind=k), ("gl",), lambda s: finance.aging(s, k), refresh)


@frappe.whitelist(methods=["GET", "POST"])
def party_invoices(party: str, kind: str = "receivable", company: str | None = None, preset: str | None = "this_month", from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
    """The open items behind one party's aging row (ERPNext's detailed receivable / payable report). Not cached."""
    require_login()
    k = _kind(kind)
    p = require_str(party, "party")
    s = scope.resolve_scope(company, preset, from_date, to_date, 0)
    queries.guard("gl")
    return ok(finance.party_invoices(s, k, p), meta=s.meta())
