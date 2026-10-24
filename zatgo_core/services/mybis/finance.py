"""Finance screen: ERPNext's own financial reports (P&L, Balance Sheet, Cash Flow, receivable / payable aging) reshaped for the app,
plus ledger-based headline figures and monthly trends.

The statements are NOT recomputed here: `erpnext.accounts.report.*.execute` is the authority (the same code behind ERPNext's
Desk reports), run only for users who may use that Report (`Report.is_permitted`). This module renames rows, strips ERPNext's
display quoting, merges the previous period and drops nothing else. Headline KPIs and trends come from the General Ledger with the
same definitions as the dashboard, and the integration tests check them against the reports.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, getdate

from zatgo_core.services.mybis import metrics, queries
from zatgo_core.services.mybis.scope import Scope

REPORT_PNL = "Profit and Loss Statement"
REPORT_BS = "Balance Sheet"
REPORT_CF = "Cash Flow"
REPORT_AR = "Accounts Receivable Summary"
REPORT_AP = "Accounts Payable Summary"
REPORT_AR_DETAIL = "Accounts Receivable"
REPORT_AP_DETAIL = "Accounts Payable"

_MODULES = {
    REPORT_PNL: "erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement",
    REPORT_BS: "erpnext.accounts.report.balance_sheet.balance_sheet",
    REPORT_CF: "erpnext.accounts.report.cash_flow.cash_flow",
    REPORT_AR: "erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary",
    REPORT_AP: "erpnext.accounts.report.accounts_payable_summary.accounts_payable_summary",
    REPORT_AR_DETAIL: "erpnext.accounts.report.accounts_receivable.accounts_receivable",
    REPORT_AP_DETAIL: "erpnext.accounts.report.accounts_payable.accounts_payable",
}


def _execute(report: str, filters: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    """(columns, data, summary) of an ERPNext report, after checking the caller may use that Report."""
    if not frappe.get_doc("Report", report).is_permitted():
        frappe.throw(_("You do not have permission to use the {0} report.").format(_(report)), frappe.PermissionError)
    res = frappe.get_module(_MODULES[report]).execute(frappe._dict(filters))
    summary = res[4] if len(res) > 4 and res[4] else []
    return res[0], res[1] or [], summary


def _statement_filters(company: str, start: date, end: date, periodicity: str) -> dict[str, Any]:
    return {
        "company": company,
        "filter_based_on": "Date Range",
        "period_start_date": start,
        "period_end_date": end,
        "periodicity": periodicity,
        "accumulated_values": 0,
        "presentation_currency": None,
        "include_default_book_entries": 1,
    }


def _label_of(row: dict[str, Any]) -> str:
    raw = row.get("account_name") or row.get("section_name") or row.get("account") or row.get("section") or ""
    return str(raw).strip("'")


def statement_rows(data: list[dict], value_key: str) -> list[dict[str, Any]]:
    """ERPNext statement rows -> [{key, label, indent, kind (group|account|total), value}]; blank spacer rows dropped."""
    out: list[dict[str, Any]] = []
    for r in data:
        if not r:
            continue
        raw = str(r.get("account_name") or r.get("section_name") or r.get("account") or r.get("section") or "")
        if not raw:
            continue
        label = raw.strip("'")
        value = r.get(value_key)
        indent = r.get("indent")
        is_total = raw.startswith("'") and indent is None
        if is_total:
            kind = "total"
        elif r.get("is_group") or value is None:
            kind = "group"
        else:
            kind = "account"
        out.append(
            {
                "key": label if is_total else str(r.get("account") or r.get("section") or label),
                "label": label,
                "indent": int(indent or 0),
                "kind": kind,
                "value": None if value is None else round(flt(value), 2),
            }
        )
    return out


def merge_previous(rows: list[dict], previous: list[dict] | None) -> list[dict]:
    before = {r["key"]: r["value"] for r in previous or []}
    for r in rows:
        prev = before.get(r["key"]) if previous is not None else None
        r["previous_value"] = prev
        r["growth_percent"] = None if r["value"] is None or prev is None else metrics.metric(r["value"], prev)["growth_percent"]
    return rows


def _summary_map(summary: list[dict]) -> list[dict[str, Any]]:
    return [{"label": s.get("label"), "value": round(flt(s.get("value")), 2), "indicator": s.get("indicator")} for s in summary]


def as_of(scope: Scope) -> date:
    """Balances and aging are positions: for a period that has not ended yet they are as of today, never of a future date."""
    return min(scope.current.to_date, getdate(frappe.utils.today()))


def _fiscal_start(company: str, on: date) -> date:
    from erpnext.accounts.utils import get_fiscal_year

    return getdate(get_fiscal_year(on, company=company)[1])


def profit_and_loss(scope: Scope) -> dict[str, Any]:
    def run(start: date, end: date):
        _cols, data, summary = _execute(REPORT_PNL, _statement_filters(scope.company, start, end, "Monthly"))
        return statement_rows(data, "total"), summary

    cur_rows, cur_sum = run(scope.current.from_date, scope.current.to_date)
    prev_rows = prev_sum = None
    if scope.previous:
        prev_rows, prev_sum = run(scope.previous.from_date, scope.previous.to_date)
    return {
        "currency": scope.currency,
        "report": REPORT_PNL,
        "rows": merge_previous(cur_rows, prev_rows),
        "summary": _summary_map(cur_sum),
        "previous_summary": None if prev_sum is None else _summary_map(prev_sum),
    }


def balance_sheet(scope: Scope) -> dict[str, Any]:
    """Balances as of the period's end (and of the previous period's end)."""

    def run(end: date):
        start = _fiscal_start(scope.company, end)
        _cols, data, summary = _execute(REPORT_BS, _statement_filters(scope.company, start, end, "Yearly"))
        return statement_rows(data, "total"), summary

    cur_rows, cur_sum = run(as_of(scope))
    prev_rows = prev_sum = None
    if scope.previous:
        prev_rows, prev_sum = run(scope.previous.to_date)
    return {
        "currency": scope.currency,
        "report": REPORT_BS,
        "as_of": as_of(scope).isoformat(),
        "rows": merge_previous(cur_rows, prev_rows),
        "summary": _summary_map(cur_sum),
        "previous_summary": None if prev_sum is None else _summary_map(prev_sum),
    }


def cash_flow(scope: Scope) -> dict[str, Any]:
    def run(start: date, end: date):
        _cols, data, summary = _execute(REPORT_CF, _statement_filters(scope.company, start, end, "Monthly"))
        return statement_rows(data, "total"), summary

    cur_rows, cur_sum = run(scope.current.from_date, scope.current.to_date)
    prev_rows = prev_sum = None
    if scope.previous:
        prev_rows, prev_sum = run(scope.previous.from_date, scope.previous.to_date)
    return {
        "currency": scope.currency,
        "report": REPORT_CF,
        "rows": merge_previous(cur_rows, prev_rows),
        "summary": _summary_map(cur_sum),
        "previous_summary": None if prev_sum is None else _summary_map(prev_sum),
    }


# -- aging -------------------------------------------------------------------------------------------------------------

AGING_BUCKETS = (
    ("not_due", "Not due", ("range0",)),
    ("d0_30", "0-30", ("range1",)),
    ("d31_60", "31-60", ("range2",)),
    ("d61_90", "61-90", ("range3",)),
    ("d90_plus", "90+", ("range4", "range5")),
)


def _aging_filters(company: str, as_of: date, party_type: str) -> dict[str, Any]:
    return {
        "company": company,
        "report_date": as_of,
        "ageing_based_on": "Due Date",
        "range1": 30,
        "range2": 60,
        "range3": 90,
        "range4": 120,
        "party_type": party_type,
    }


def _bucket_values(row: dict[str, Any]) -> dict[str, float]:
    return {key: round(sum(flt(row.get(f)) for f in fields), 2) for key, _label, fields in AGING_BUCKETS}


def aging(scope: Scope, kind: str) -> dict[str, Any]:
    """Receivable / payable aging as of the period's end: totals per bucket and the parties, most overdue first."""
    party_type, report = ("Customer", REPORT_AR) if kind == "receivable" else ("Supplier", REPORT_AP)
    _cols, data, _summary = _execute(report, _aging_filters(scope.company, as_of(scope), party_type))
    parties = []
    totals = OrderedDict((key, 0.0) for key, _l, _f in AGING_BUCKETS)
    outstanding = 0.0
    for r in data:
        if not r.get("party"):
            continue
        buckets = _bucket_values(r)
        out = round(flt(r.get("outstanding")), 2)
        overdue = round(sum(v for k, v in buckets.items() if k != "not_due"), 2)
        for k, v in buckets.items():
            totals[k] += v
        outstanding += out
        parties.append({"party": r["party"], "outstanding": out, "overdue": overdue, "buckets": buckets})
    parties.sort(key=lambda p: (-p["overdue"], -p["outstanding"], p["party"]))
    return {
        "currency": scope.currency,
        "kind": kind,
        "as_of": as_of(scope).isoformat(),
        "report": report,
        "outstanding": round(outstanding, 2),
        "buckets": [{"key": k, "label": label, "value": round(totals[k], 2)} for k, label, _f in AGING_BUCKETS],
        "parties": parties,
    }


def party_invoices(scope: Scope, kind: str, party: str) -> dict[str, Any]:
    """The open items behind one party's aging row (ERPNext's detailed receivable / payable report)."""
    party_type, report = ("Customer", REPORT_AR_DETAIL) if kind == "receivable" else ("Supplier", REPORT_AP_DETAIL)
    f = _aging_filters(scope.company, as_of(scope), party_type)
    f["party"] = [party]
    _cols, data, _summary = _execute(report, f)
    rows = []
    for r in data:
        if not r.get("voucher_no"):
            continue
        rows.append(
            {
                "voucher_type": r.get("voucher_type"),
                "voucher_no": r.get("voucher_no"),
                "posting_date": str(r.get("posting_date") or ""),
                "due_date": str(r.get("due_date") or ""),
                "invoiced": round(flt(r.get("invoiced")), 2),
                "paid": round(flt(r.get("paid")), 2),
                "credit_note": round(flt(r.get("credit_note")), 2),
                "outstanding": round(flt(r.get("outstanding")), 2),
                "age": int(flt(r.get("age"))),
                "buckets": _bucket_values(r),
            }
        )
    rows.sort(key=lambda x: (-x["age"], x["voucher_no"]))
    return {"currency": scope.currency, "kind": kind, "party": party, "as_of": as_of(scope).isoformat(), "rows": rows}


# -- ledger headline figures and trends ------------------------------------------------------------------------------


def _balance_of_types(company: str, types: tuple[str, ...], as_of: date) -> float:
    row = frappe.db.sql(
        """
        SELECT COALESCE(SUM(gle.debit - gle.credit), 0) FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.company = %(company)s AND gle.is_cancelled = 0 AND gle.posting_date <= %(as_of)s AND acc.account_type IN %(types)s
        """,
        {"company": company, "as_of": as_of, "types": types},
    )
    return flt(row[0][0])


def kpis(scope: Scope) -> dict[str, Any]:
    cur, prev = scope.current, scope.previous
    pnl_c = queries.gl_pnl(scope.company, cur.from_date, cur.to_date)
    pnl_p = queries.gl_pnl(scope.company, prev.from_date, prev.to_date) if prev else None

    def g(d: dict | None, key: str):
        return None if d is None else d[key]

    gross_c = pnl_c["income"] - pnl_c["cogs"]
    gross_p = None if pnl_p is None else pnl_p["income"] - pnl_p["cogs"]
    out: dict[str, Any] = {
        "currency": scope.currency,
        "revenue": metrics.metric(pnl_c["income"], g(pnl_p, "income")),
        "cogs": metrics.metric(pnl_c["cogs"], g(pnl_p, "cogs"), higher_is_better=False),
        "gross_profit": metrics.metric(gross_c, gross_p, margin_percent=metrics.percent(gross_c, pnl_c["income"])),
        "expenses": metrics.metric(pnl_c["expenses"], g(pnl_p, "expenses"), higher_is_better=False),
        "net_profit": metrics.metric(pnl_c["net_profit"], g(pnl_p, "net_profit"), margin_percent=metrics.percent(pnl_c["net_profit"], pnl_c["income"])),
    }

    def bal(types: tuple[str, ...], sign: int = 1):
        c = sign * _balance_of_types(scope.company, types, as_of(scope))
        p = sign * _balance_of_types(scope.company, types, prev.to_date) if prev else None
        return c, p

    for key, types, sign, better in (
        ("cash_balance", ("Cash",), 1, True),
        ("bank_balance", ("Bank",), 1, True),
        ("receivables", ("Receivable",), 1, False),
        ("payables", ("Payable",), -1, False),
    ):
        c, p = bal(types, sign)
        out[key] = metrics.metric(c, p, higher_is_better=better, as_of=as_of(scope).isoformat())
    return out


def _month_starts(end: date, months: int) -> list[date]:
    out = []
    y, m = end.year, end.month
    for _i in range(months):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def trends(scope: Scope, months: int = 12) -> dict[str, Any]:
    """Monthly series for the `months` months ending with the period's end month: revenue, expenses, profit, and month-end
    receivables, payables and cash + bank."""
    months = max(2, min(int(months or 12), 36))
    starts = _month_starts(scope.current.to_date, months)
    first, last = starts[0], scope.current.to_date
    pnl = frappe.db.sql(
        """
        SELECT DATE_FORMAT(gle.posting_date, '%%Y-%%m-01') AS m,
          COALESCE(SUM(CASE WHEN acc.root_type = 'Income' THEN gle.credit - gle.debit END), 0) AS income,
          COALESCE(SUM(CASE WHEN acc.root_type = 'Expense' THEN gle.debit - gle.credit END), 0) AS expense
        FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.company = %(company)s AND gle.is_cancelled = 0 AND gle.posting_date BETWEEN %(start)s AND %(end)s
          AND gle.voucher_type != 'Period Closing Voucher'
        GROUP BY m
        """,
        {"company": scope.company, "start": first, "end": last},
        as_dict=True,
    )
    by_month = {str(r.m): r for r in pnl}

    def balances(types: tuple[str, ...], sign: int) -> dict[str, float]:
        moves = frappe.db.sql(
            """
            SELECT DATE_FORMAT(gle.posting_date, '%%Y-%%m-01') AS m, COALESCE(SUM(gle.debit - gle.credit), 0) AS net
            FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.company = %(company)s AND gle.is_cancelled = 0 AND gle.posting_date BETWEEN %(start)s AND %(end)s AND acc.account_type IN %(types)s
            GROUP BY m
            """,
            {"company": scope.company, "start": first, "end": last, "types": types},
            as_dict=True,
        )
        net = {str(r.m): flt(r.net) for r in moves}
        running = _balance_of_types(scope.company, types, first - timedelta(days=1))
        out = {}
        for s in starts:
            running += net.get(s.isoformat(), 0.0)
            out[s.isoformat()] = round(sign * running, 2)
        return out

    recv, pay, cash = balances(("Receivable",), 1), balances(("Payable",), -1), balances(("Cash", "Bank"), 1)
    points = []
    for s in starts:
        k = s.isoformat()
        income = flt(by_month[k].income) if k in by_month else 0.0
        expense = flt(by_month[k].expense) if k in by_month else 0.0
        points.append(
            {
                "month": k,
                "revenue": round(income, 2),
                "expenses": round(expense, 2),
                "net_profit": round(income - expense, 2),
                "receivables": recv[k],
                "payables": pay[k],
                "cash": cash[k],
            }
        )
    return {"currency": scope.currency, "months": months, "points": points}
