"""The MyBis daily report: one day's sales, purchases, money in and out, and where receivables and payables stand.

`build(scope)` is the figures (the app opens it on demand); `send_due()` is the scheduled push of it to the users who opted in. The
figures reuse the dashboard's own definitions (`dashboard.sales_summary` / `purchase_summary`) so the report can never disagree with
the screens it summarises. Each section answers `{"available": False}` when the caller may not read its source instead of failing
the whole report, and `overdue` is left out where ERPNext's aging report cannot be run.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import fmt_money, getdate

from zatgo_core.services import app_state
from zatgo_core.services.mybis import dashboard, delivery, finance, metrics, notify_prefs, queries, scope as scopes
from zatgo_core.zatgo_core.doctype.zg_mybis_settings import zg_mybis_settings

UNAVAILABLE = {"available": False}


def report_date(now: datetime, hour: int) -> date:
    """The day a report sent at `hour` covers: from midday on, the day so far; in the morning, the day that just ended."""
    return now.date() if hour >= 12 else now.date() - timedelta(days=1)


def day_scope(company: str | None, day: Any) -> scopes.Scope:
    """A one-day scope compared with the day before."""
    return scopes.resolve_scope(company, "custom", day, day, 1)


def _can(kind: str) -> bool:
    return bool(frappe.has_permission(queries.SOURCE_DOCTYPES[kind], "read"))


def _money_flow(scope: scopes.Scope) -> dict[str, Any]:
    if not _can("payments"):
        return {"received": UNAVAILABLE, "paid": UNAVAILABLE, "net_cash": UNAVAILABLE}
    cur, prev = scope.current, scope.previous
    c = queries.payment_totals(scope.company, cur.from_date, cur.to_date)
    p = queries.payment_totals(scope.company, prev.from_date, prev.to_date) if prev else None

    def m(key: str, **kw):
        return metrics.metric(c[key], None if p is None else p[key], **kw)

    net_c = c["received"] - c["paid"]
    net_p = None if p is None else p["received"] - p["paid"]
    return {
        "received": m("received", count=c["receipts"]),
        "paid": m("paid", higher_is_better=False, count=c["payments"]),
        "net_cash": metrics.metric(net_c, net_p),
    }


def _balance(scope: scopes.Scope, account_type: str, kind: str) -> dict[str, Any]:
    if not _can("gl"):
        return dict(UNAVAILABLE)
    cur, prev = scope.current, scope.previous
    sign = 1 if kind == "receivable" else -1
    day = finance.as_of(scope)
    out = metrics.metric(
        sign * queries.balance_as_of(scope.company, account_type, day),
        None if prev is None else sign * queries.balance_as_of(scope.company, account_type, prev.to_date),
        higher_is_better=False,
        as_of=day.isoformat(),
    )
    try:
        out["overdue"] = round(sum(p["overdue"] for p in finance.aging(scope, kind)["parties"]), 2)
    except Exception:
        out["overdue"] = None
    return out


def build(scope: scopes.Scope) -> dict[str, Any]:
    """The report for `scope` (a single day)."""
    sales = dashboard.sales_summary(scope) if _can("sales") else None
    purchases = dashboard.purchase_summary(scope) if _can("purchases") else None
    flow = _money_flow(scope)
    return {
        "currency": scope.currency,
        "date": scope.current.from_date.isoformat(),
        "sales": (
            {k: sales[k] for k in ("net_sales", "invoices", "returns", "paid_sales", "credit_sales")} if sales else dict(UNAVAILABLE)
        ),
        "purchases": ({k: purchases[k] for k in ("net_purchases", "invoices", "returns")} if purchases else dict(UNAVAILABLE)),
        "money": flow,
        "receivable": _balance(scope, "Receivable", "receivable"),
        "payable": _balance(scope, "Payable", "payable"),
    }


def _val(block: Any, key: str | None = None) -> float | None:
    node = block if key is None else (block or {}).get(key)
    return None if not isinstance(node, dict) else node.get("value")


def lines(report: dict[str, Any], money=None) -> list[tuple[str, str]]:
    """(label, text) rows of a report for a notification or e-mail -- pure; `money` formats an amount (default: plain 2 places)."""
    fmt = money or (lambda v: f"{v:,.2f}")

    def row(label: str, value: float | None, count: bool = False) -> tuple[str, str]:
        if value is None:
            return (label, "—")
        return (label, str(int(value)) if count else fmt(value))

    sales, purchases, flow = report["sales"], report["purchases"], report["money"]
    return [
        row(_("Sales (net)"), _val(sales, "net_sales")),
        row(_("Sales invoices"), _val(sales, "invoices"), count=True),
        row(_("Purchases (net)"), _val(purchases, "net_purchases")),
        row(_("Purchase invoices"), _val(purchases, "invoices"), count=True),
        row(_("Received from customers"), _val(flow, "received")),
        row(_("Paid to suppliers"), _val(flow, "paid")),
        row(_("Net cash movement"), _val(flow, "net_cash")),
        row(_("Receivable balance"), _val(report["receivable"])),
        row(_("Payable balance"), _val(report["payable"])),
    ]


def subject_for(company: str, day: Any) -> str:
    return f"Daily report · {company} · {getdate(day).isoformat()}"


def _html(subject: str, rows: list[tuple[str, str]]) -> str:
    body = "".join(f"<tr><td style='padding:4px 12px 4px 0'>{frappe.utils.escape_html(a)}</td><td style='text-align:right'><b>{frappe.utils.escape_html(b)}</b></td></tr>" for a, b in rows)
    return f"<h3>{frappe.utils.escape_html(subject)}</h3><table>{body}</table>"


def _send_one(user: str, company: str, day: date, email: bool) -> bool:
    """Build and deliver one user's report for one company; False if it was already sent or the user may not see MyBis figures."""
    subject = subject_for(company, day)
    if delivery.already_sent(user, subject):
        return False
    scope = day_scope(company, day)
    queries.guard()
    report = build(scope)
    rows = lines(report, lambda v: fmt_money(v, currency=scope.currency))
    delivery.notify(user, subject, "\n".join(f"{a}: {b}" for a, b in rows))
    if email:
        delivery.email(user, subject, _html(subject, rows))
    return True


def send_due(now: datetime | None = None) -> int:
    """Hourly scheduler entry: at the configured hour, send each opted-in user the report of each company they can read. Returns how
    many reports were sent. Safe to run any number of times in the hour (a report already sent is skipped)."""
    if not app_state.is_on("mybis"):
        return 0
    admin = zg_mybis_settings.policy()["notifications"]
    now = now or frappe.utils.now_datetime()
    if not admin["daily_report"] or now.hour != admin["report_hour"]:
        return 0
    day = report_date(now, admin["report_hour"])
    sent = 0
    me = frappe.session.user
    try:
        for user in notify_prefs.recipients("daily_report"):
            email = admin["report_email"] and user in notify_prefs.recipients("report_email")
            frappe.set_user(user)  # MyBis figures are computed as, and limited to, the reader
            try:
                for company in [c["name"] for c in scopes.readable_companies()]:
                    point = "mybis_daily_report"
                    frappe.db.savepoint(point)
                    try:
                        sent += _send_one(user, company, day, email)
                    except Exception:
                        frappe.db.rollback(save_point=point)
                        frappe.log_error(title=f"MyBis daily report failed for {user}", message=frappe.get_traceback())
            finally:
                frappe.set_user(me)
    finally:
        frappe.set_user(me)
    return sent
