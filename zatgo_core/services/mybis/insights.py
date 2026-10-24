"""Business insights and alerts: rules over real ERPNext figures, each producing a traceable statement.

Every item says what was measured (metric, current vs previous value), how (`calculation`, plain text), from which data (`source`,
`data` rows) and where to look next (`drill`, a destination the app opens). Nothing is invented or smoothed: a rule that cannot
read its source (no permission, no previous period) produces nothing.

Alerts are risks that call for action (declines, losses, overdue money, stock problems); insights are observations (growth, mix,
concentration). Severity is critical / high / medium / low by fixed thresholds below. Ids are stable (`rule` or `rule:key`), so the
same condition keeps the same `fingerprint` from one run to the next -- the hook a future push-notification job needs to notify
only on change; no push is sent from here.

Like-for-like: while the selected period is unfinished (this month so far) it is compared with the same number of days at the start
of the previous period, not with the whole previous period.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any, Callable

import frappe
from frappe.utils import flt, getdate

from zatgo_core.services.mybis import breakdown, dashboard, finance, forecasting, inventory, metrics, queries
from zatgo_core.services.mybis import period as periods
from zatgo_core.services.mybis.scope import Scope

SEVERITIES = ("critical", "high", "medium", "low")
RANK = {s: i for i, s in enumerate(SEVERITIES)}

# thresholds (percent unless stated)
SALES_DROP = ((-30, "critical"), (-20, "high"), (-10, "medium"))
SALES_GROWTH = 20
MARGIN_DROP_PP = ((10, "critical"), (6, "high"), (3, "medium"))
MARGIN_RISE_PP = 3
EXPENSE_GROWTH = ((50, "high"), (25, "medium"))
RECEIVABLES_GROWTH = ((50, "high"), (20, "medium"))
OVERDUE_SHARE = 50  # % of outstanding that is overdue
CATEGORY_SHARE = 30
CATEGORY_CONCENTRATION = 60
MOVER_MIN_SHARE = 5
MOVER_GROWTH = 30
MOVER_DROP = ((-50, "high"), (-30, "medium"))
CUSTOMER_CONCENTRATION = 40
STOCK_VALUE_SHARE = 20
INVENTORY_FLAT = 5
INVENTORY_GROWTH = 20


def _severity(value: float, table: tuple[tuple[float, str], ...], below: bool = False) -> str | None:
    for limit, sev in table:
        if (value <= limit) if below else (value >= limit):
            return sev
    return None


def comparable(scope: Scope, today: date) -> tuple[Scope, str | None]:
    """The scope to compare: when the current period has not ended, the previous period is cut to the same number of days."""
    cur, prev = scope.current, scope.previous
    if prev is None:
        return scope, None
    if cur.to_date <= today:
        return scope, None
    elapsed = (min(cur.to_date, today) - cur.from_date).days + 1
    prev_end = min(prev.to_date, prev.from_date + timedelta(days=elapsed - 1))
    return (
        replace(scope, current=periods.Period(cur.from_date, min(cur.to_date, today)), previous=periods.Period(prev.from_date, prev_end)),
        f"{cur.from_date:%b %d} - {min(cur.to_date, today):%b %d} compared with the same {elapsed} day{'s' if elapsed != 1 else ''} of the previous period "
        f"({prev.from_date:%b %d} - {prev_end:%b %d}).",
    )


def _can(*kinds: str) -> bool:
    return all(frappe.has_permission(queries.SOURCE_DOCTYPES[k], "read") for k in kinds)


def make(
    id_: str,
    typ: str,
    severity: str,
    category: str,
    title: str,
    description: str,
    *,
    metric_key: str,
    metric_label: str,
    unit: str,
    current: float | None,
    previous: float | None = None,
    source: str,
    calculation: str,
    data: list[dict[str, Any]] | None = None,
    drill: dict[str, Any] | None = None,
    currency: str = "",
) -> dict[str, Any]:
    change = None if current is None or previous is None else round(current - previous, 2)
    return {
        "id": id_,
        "type": typ,
        "severity": severity,
        "category": category,
        "title": title,
        "description": description,
        "metric": {"key": metric_key, "label": metric_label, "unit": unit},
        "current_value": None if current is None else round(current, 2),
        "previous_value": None if previous is None else round(previous, 2),
        "change": change,
        "change_percent": None if current is None or previous is None else periods.growth_percent(current, previous),
        "currency": currency,
        "source": source,
        "calculation": calculation,
        "data": data or [],
        "drill": drill or {"screen": "dashboard"},
    }


def _money(v: float, cur: str) -> str:
    return f"{cur} {v:,.0f}" if abs(v) >= 1000 else f"{cur} {v:,.2f}"


def _pct(v: float) -> str:
    return f"{abs(v):.0f}%" if abs(v) >= 10 else f"{abs(v):.1f}%"


# -- rules -------------------------------------------------------------------------------------------------------------


class Ctx:
    def __init__(self, scope: Scope, today: date):
        self.scope = scope
        self.today = today
        self.cur = scope.currency
        self._kpis: dict[str, Any] | None = None
        self._cache: dict[str, Any] = {}

    @property
    def kpis(self) -> dict[str, Any]:
        if self._kpis is None:
            self._kpis = dashboard.kpis(self.scope)
        return self._kpis

    def kpi(self, key: str) -> dict[str, Any] | None:
        k = self.kpis.get(key)
        return k if isinstance(k, dict) and k.get("available", True) and k.get("value") is not None else None

    def memo(self, key: str, fn: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def ranking(self, side: str, dimension: str, limit: int = 10) -> dict[str, Any]:
        s = self.scope
        cur = (s.current.from_date, s.current.to_date)
        prev = (s.previous.from_date, s.previous.to_date) if s.previous else None
        return self.memo(f"rank:{side}:{dimension}", lambda: breakdown.breakdown(side, s.company, cur, prev, dimension, {}, limit, "revenue"))

    def aging(self, kind: str) -> dict[str, Any]:
        return self.memo(f"aging:{kind}", lambda: finance.aging(self.scope, kind))

    def stock(self) -> dict[str, Any]:
        return self.memo("stock", lambda: inventory.summary(self.scope.company, self.today))


def rule_sales_change(c: Ctx) -> list[dict]:
    k = c.kpi("net_sales")
    if not k or k["previous_value"] is None or not k["previous_value"] or k["growth_percent"] is None:
        return []
    g = k["growth_percent"]
    data = [{"label": "Net sales", "value": k["value"], "previous_value": k["previous_value"], "unit": "currency"}]
    common = dict(
        metric_key="net_sales", metric_label="Net sales", unit="currency", current=k["value"], previous=k["previous_value"], currency=c.cur,
        source="Sales Invoices (submitted, net of returns, before tax)",
        calculation="(net sales this period - net sales previous period) / net sales previous period",
        data=data, drill={"screen": "sales"},
    )
    sev = _severity(g, SALES_DROP, below=True)
    if sev:
        return [make("sales_decline", "alert", sev, "sales", f"Net sales fell {_pct(g)}", f"Net sales were {_money(k['value'], c.cur)} against {_money(k['previous_value'], c.cur)} in the previous period.", **common)]
    if g >= SALES_GROWTH:
        return [make("sales_growth", "insight", "low", "sales", f"Net sales grew {_pct(g)}", f"Net sales were {_money(k['value'], c.cur)} against {_money(k['previous_value'], c.cur)} in the previous period.", **common)]
    return []


def rule_profit(c: Ctx) -> list[dict]:
    k = c.kpi("net_profit")
    if not k:
        return []
    cur_v, prev_v = k["value"], k["previous_value"]
    common = dict(
        metric_key="net_profit", metric_label="Net profit", unit="currency", current=cur_v, previous=prev_v, currency=c.cur,
        source="General Ledger (Income - Cost of Goods Sold - Expenses)",
        calculation="Income account credits minus Cost of Goods Sold and other Expense account debits in the period",
        data=[{"label": "Net profit", "value": cur_v, "previous_value": prev_v, "unit": "currency"}], drill={"screen": "finance", "tab": "profit_and_loss"},
    )
    if cur_v < 0:
        sev = "critical" if prev_v is not None and prev_v >= 0 else "high"
        return [make("net_loss", "alert", sev, "profit", "The business made a loss", f"Net profit was {_money(cur_v, c.cur)} in this period" + (f" (previous period: {_money(prev_v, c.cur)})." if prev_v is not None else "."), **common)]
    g = k["growth_percent"]
    if g is not None and g <= -25 and prev_v and prev_v > 0:
        return [make("profit_decline", "alert", "medium", "profit", f"Net profit fell {_pct(g)}", f"Net profit was {_money(cur_v, c.cur)} against {_money(prev_v, c.cur)} in the previous period.", **common)]
    return []


def rule_margin(c: Ctx) -> list[dict]:
    k = c.kpi("gross_profit")
    if not k or k.get("margin_percent") is None or k.get("previous_margin_percent") is None:
        return []
    now, before = k["margin_percent"], k["previous_margin_percent"]
    diff = round(now - before, 2)
    common = dict(
        metric_key="gross_margin", metric_label="Gross margin", unit="percent", current=now, previous=before, currency=c.cur,
        source=f"Net sales and cost of goods sold ({'ledger' if k.get('basis') == 'gl' else 'valuation at sale, estimated'})",
        calculation="gross profit / net sales, this period against the previous period (difference in percentage points)",
        data=[{"label": "Gross margin", "value": now, "previous_value": before, "unit": "percent"}, {"label": "Gross profit", "value": k["value"], "previous_value": k["previous_value"], "unit": "currency"}],
        drill={"screen": "sales"},
    )
    sev = _severity(-diff, MARGIN_DROP_PP)
    if sev:
        return [make("margin_decline", "alert", sev, "profit", f"Gross margin fell from {before:.0f}% to {now:.0f}%", f"Margin dropped {abs(diff):.1f} percentage points.", **common)]
    if diff >= MARGIN_RISE_PP:
        return [make("margin_improvement", "insight", "low", "profit", f"Gross margin rose from {before:.0f}% to {now:.0f}%", f"Margin improved {diff:.1f} percentage points.", **common)]
    return []


def rule_expenses(c: Ctx) -> list[dict]:
    k = c.kpi("expenses")
    if not k or not k["previous_value"] or k["growth_percent"] is None:
        return []
    sev = _severity(k["growth_percent"], EXPENSE_GROWTH)
    if not sev:
        return []
    return [make("expenses_rise", "alert", sev, "profit", f"Expenses rose {_pct(k['growth_percent'])}", f"Expenses were {_money(k['value'], c.cur)} against {_money(k['previous_value'], c.cur)} in the previous period.",
                 metric_key="expenses", metric_label="Expenses", unit="currency", current=k["value"], previous=k["previous_value"], currency=c.cur,
                 source="General Ledger (Expense accounts other than Cost of Goods Sold)", calculation="Expense account debits minus credits in the period",
                 data=[{"label": "Expenses", "value": k["value"], "previous_value": k["previous_value"], "unit": "currency"}], drill={"screen": "finance", "tab": "profit_and_loss"})]


def rule_category_mix(c: Ctx) -> list[dict]:
    d = c.ranking("sales", "category")
    rows = d["rows"]
    if not rows or d["total_revenue"] <= 0:
        return []
    out = []
    top = rows[0]
    share = top.get("share_percent")
    data = [{"label": r["name"], "value": r["revenue"], "previous_value": r.get("previous_revenue"), "unit": "currency"} for r in rows[:5]]
    if share is not None and share >= CATEGORY_SHARE:
        sev = "medium" if share >= CATEGORY_CONCENTRATION and len(rows) > 1 else "low"
        out.append(make("top_category", "insight", sev, "sales", f"{top['name']} generated {share:.0f}% of sales", f"{top['name']} brought in {_money(top['revenue'], c.cur)} of {_money(d['total_revenue'], c.cur)} net sales in this period.",
                        metric_key="category_share", metric_label=f"{top['name']} share of sales", unit="percent", current=share, previous=None, currency=c.cur,
                        source="Sales Invoice Items by item group (net of returns)", calculation="net sales of the item group / net sales of all item groups", data=data,
                        drill={"screen": "sales", "dimension": "category", "filters": {"category": top["code"]}, "title": top["name"]}))
    movers = [r for r in rows if (r.get("share_percent") or 0) >= MOVER_MIN_SHARE and r.get("growth_percent") is not None and r.get("previous_revenue")]
    for r in sorted(movers, key=lambda r: r["growth_percent"], reverse=True)[:1]:
        if r["growth_percent"] >= MOVER_GROWTH:
            out.append(make(f"category_growth:{r['code']}", "insight", "low", "sales", f"{r['name']} sales grew {_pct(r['growth_percent'])}", f"{r['name']}: {_money(r['revenue'], c.cur)} against {_money(r['previous_revenue'], c.cur)} in the previous period.",
                            metric_key="category_revenue", metric_label=f"{r['name']} net sales", unit="currency", current=r["revenue"], previous=r["previous_revenue"], currency=c.cur,
                            source="Sales Invoice Items by item group (net of returns)", calculation="net sales of the item group, this period against the previous period",
                            data=[{"label": r["name"], "value": r["revenue"], "previous_value": r["previous_revenue"], "unit": "currency"}],
                            drill={"screen": "sales", "dimension": "category", "filters": {"category": r["code"]}, "title": r["name"]}))
    for r in sorted(movers, key=lambda r: r["growth_percent"])[:1]:
        sev = _severity(r["growth_percent"], MOVER_DROP, below=True)
        if sev:
            out.append(make(f"category_decline:{r['code']}", "alert", sev, "sales", f"{r['name']} sales fell {_pct(r['growth_percent'])}", f"{r['name']}: {_money(r['revenue'], c.cur)} against {_money(r['previous_revenue'], c.cur)} in the previous period.",
                            metric_key="category_revenue", metric_label=f"{r['name']} net sales", unit="currency", current=r["revenue"], previous=r["previous_revenue"], currency=c.cur,
                            source="Sales Invoice Items by item group (net of returns)", calculation="net sales of the item group, this period against the previous period",
                            data=[{"label": r["name"], "value": r["revenue"], "previous_value": r["previous_revenue"], "unit": "currency"}],
                            drill={"screen": "sales", "dimension": "category", "filters": {"category": r["code"]}, "title": r["name"]}))
    return out


def rule_product_movers(c: Ctx) -> list[dict]:
    d = c.ranking("sales", "product")
    movers = [r for r in d["rows"] if r.get("growth_percent") is not None and r.get("previous_revenue")]
    out = []
    for r in sorted(movers, key=lambda r: r["growth_percent"], reverse=True)[:1]:
        if r["growth_percent"] >= MOVER_GROWTH:
            out.append(make(f"product_growth:{r['code']}", "insight", "low", "sales", f"{r['name']} sales grew {_pct(r['growth_percent'])}", f"{r['name']}: {_money(r['revenue'], c.cur)} against {_money(r['previous_revenue'], c.cur)} in the previous period.",
                            metric_key="product_revenue", metric_label=f"{r['name']} net sales", unit="currency", current=r["revenue"], previous=r["previous_revenue"], currency=c.cur,
                            source="Sales Invoice Items (net of returns), top 10 items by revenue", calculation="net sales of the item, this period against the previous period",
                            data=[{"label": r["name"], "value": r["revenue"], "previous_value": r["previous_revenue"], "unit": "currency"}],
                            drill={"screen": "sales", "dimension": "product", "filters": {"product": r["code"]}, "title": r["name"]}))
    return out


def rule_top_customer(c: Ctx) -> list[dict]:
    d = c.ranking("sales", "customer")
    rows = d["rows"]
    if not rows or d["total_revenue"] <= 0:
        return []
    top = rows[0]
    share = top.get("share_percent")
    if share is None:
        return []
    data = [{"label": r["name"], "value": r["revenue"], "previous_value": r.get("previous_revenue"), "unit": "currency"} for r in rows[:5]]
    drill = {"screen": "customers", "dimension": "customer", "filters": {"customer": top["code"]}, "title": top["name"]}
    common = dict(metric_key="customer_share", metric_label=f"{top['name']} share of sales", unit="percent", current=share, previous=None, currency=c.cur,
                  source="Sales Invoices by customer (net of returns)", calculation="net sales to the customer / net sales to all customers", data=data, drill=drill)
    if share >= CUSTOMER_CONCENTRATION and len(rows) > 1:
        return [make("customer_concentration", "alert", "medium", "customers", f"{top['name']} is {share:.0f}% of your sales", f"One customer accounts for {_money(top['revenue'], c.cur)} of {_money(d['total_revenue'], c.cur)} net sales: losing them would hurt.", **common)]
    return [make("top_customer", "insight", "low", "customers", f"{top['name']} is your highest-value customer", f"{top['name']} bought {_money(top['revenue'], c.cur)} ({share:.0f}% of net sales) in this period.", **common)]


def rule_receivables(c: Ctx) -> list[dict]:
    out = []
    k = c.kpi("receivables")
    if k and k["previous_value"] and k["growth_percent"] is not None and k["value"] > 0:
        sev = _severity(k["growth_percent"], RECEIVABLES_GROWTH)
        if sev:
            out.append(make("receivables_rise", "alert", sev, "finance", f"Receivables rose {_pct(k['growth_percent'])}", f"Customers owe {_money(k['value'], c.cur)}, up from {_money(k['previous_value'], c.cur)}.",
                            metric_key="receivables", metric_label="Receivables", unit="currency", current=k["value"], previous=k["previous_value"], currency=c.cur,
                            source="General Ledger balance of Receivable accounts", calculation="Receivable account balance at the end of the period against the end of the previous period",
                            data=[{"label": "Receivables", "value": k["value"], "previous_value": k["previous_value"], "unit": "currency"}], drill={"screen": "finance", "tab": "receivable"}))
    a = c.aging("receivable")
    if a["outstanding"] > 0:
        b = {x["key"]: x["value"] for x in a["buckets"]}
        overdue = round(sum(v for key, v in b.items() if key != "not_due"), 2)
        share = overdue / a["outstanding"] * 100 if a["outstanding"] else 0
        if share >= OVERDUE_SHARE:
            sev = "high" if b.get("d90_plus", 0) / a["outstanding"] >= 0.25 else "medium"
            out.append(make("receivables_overdue", "alert", sev, "finance", f"{share:.0f}% of receivables are overdue", f"{_money(overdue, c.cur)} of {_money(a['outstanding'], c.cur)} is past its due date, {_money(b.get('d90_plus', 0), c.cur)} by more than 90 days.",
                            metric_key="overdue_receivables", metric_label="Overdue receivables", unit="currency", current=overdue, previous=None, currency=c.cur,
                            source="ERPNext Accounts Receivable Summary (ageing by due date)", calculation="amount outside the 'Not due' bucket / total outstanding",
                            data=[{"label": x["label"], "value": x["value"], "unit": "currency"} for x in a["buckets"]], drill={"screen": "finance", "tab": "receivable"}))
        worst = next((p for p in a["parties"] if p["overdue"] > 0), None)
        if worst:
            sev = "high" if worst["buckets"].get("d90_plus", 0) > 0 else "medium"
            out.append(make(f"customer_overdue:{worst['party']}", "alert", sev, "customers", f"{worst['party']} has overdue invoices", f"{_money(worst['overdue'], c.cur)} is overdue out of {_money(worst['outstanding'], c.cur)} owed; they are your most overdue customer.",
                            metric_key="customer_overdue", metric_label=f"{worst['party']} overdue", unit="currency", current=worst["overdue"], previous=None, currency=c.cur,
                            source="ERPNext Accounts Receivable Summary (ageing by due date)", calculation="outstanding invoices of the customer past their due date",
                            data=[{"label": x["label"], "value": worst["buckets"].get(x["key"], 0.0), "unit": "currency"} for x in a["buckets"]],
                            drill={"screen": "finance", "tab": "receivable", "party": worst["party"]}))
    return out


def rule_payables(c: Ctx) -> list[dict]:
    a = c.aging("payable")
    if a["outstanding"] <= 0:
        return []
    b = {x["key"]: x["value"] for x in a["buckets"]}
    overdue = round(sum(v for key, v in b.items() if key != "not_due"), 2)
    share = overdue / a["outstanding"] * 100
    if share < 30:
        return []
    return [make("payables_overdue", "alert", "medium", "finance", f"{share:.0f}% of payables are overdue", f"You owe suppliers {_money(a['outstanding'], c.cur)}, of which {_money(overdue, c.cur)} is past due.",
                 metric_key="overdue_payables", metric_label="Overdue payables", unit="currency", current=overdue, previous=None, currency=c.cur,
                 source="ERPNext Accounts Payable Summary (ageing by due date)", calculation="amount outside the 'Not due' bucket / total outstanding",
                 data=[{"label": x["label"], "value": x["value"], "unit": "currency"} for x in a["buckets"]], drill={"screen": "finance", "tab": "payable"})]


def rule_cash_cover(c: Ctx) -> list[dict]:
    bal = forecasting.balance_now(c.scope.company, c.today)
    due = forecasting.due_between(c.scope.company, c.today, c.today + timedelta(days=30))["payables_due"]
    if due <= 0 or bal >= due:
        return []
    return [make("cash_cover", "alert", "high", "finance", "Cash may not cover the next 30 days of payables", f"Cash and bank hold {_money(bal, c.cur)} but supplier invoices of {_money(due, c.cur)} fall due within 30 days.",
                 metric_key="cash_balance", metric_label="Cash + bank balance", unit="currency", current=bal, previous=None, currency=c.cur,
                 source="General Ledger (Cash and Bank accounts) and open Purchase Invoices by due date",
                 calculation="cash + bank balance today against the outstanding of purchase invoices due in the next 30 days (receipts from customers are not counted)",
                 data=[{"label": "Cash + bank", "value": bal, "unit": "currency"}, {"label": "Payables due in 30 days", "value": due, "unit": "currency"}], drill={"screen": "finance", "tab": "payable"})]


def rule_inventory(c: Ctx) -> list[dict]:
    s = c.stock()
    n = s["counts"]
    value = s["stock_value"]
    out = []

    def alert(id_: str, sev: str, title: str, desc: str, count: int, kind: str, calc: str) -> dict:
        return make(id_, "alert", sev, "inventory", title, desc, metric_key=id_, metric_label=title, unit="count", current=count, previous=None, currency=c.cur,
                    source="Bin (current stock) and Item Reorder levels", calculation=calc,
                    data=[{"label": "Items", "value": count, "unit": "count"}], drill={"screen": "inventory", "kind": kind})

    if n["out_of_stock"] > 0:
        out.append(alert("out_of_stock", "high" if n["out_of_stock"] >= 10 else "medium", f"{n['out_of_stock']} product{'s are' if n['out_of_stock'] != 1 else ' is'} out of stock", "Stocked items whose balance is zero in every warehouse.", n["out_of_stock"], "out_of_stock", "stocked items with a total balance of 0"))
    if n["low_stock"] > 0:
        out.append(alert("low_stock", "high" if n["low_stock"] >= 10 else "medium", f"{n['low_stock']} product{'s are' if n['low_stock'] != 1 else ' is'} below the reorder level", "Items at or below the reorder level set on the item.", n["low_stock"], "low_stock", "bins at or below the Item Reorder level (levels set above 0)"))
    if n["negative"] > 0:
        out.append(alert("negative_stock", "high", f"{n['negative']} product{'s have' if n['negative'] != 1 else ' has'} negative stock", "A negative balance means stock was issued before it was received: the stock records need correcting.", n["negative"], "negative", "bins with a balance below 0"))
    if value > 0 and s["dead_value"] / value * 100 >= STOCK_VALUE_SHARE:
        share = s["dead_value"] / value * 100
        out.append(make("dead_stock", "alert", "medium", "inventory", f"{share:.0f}% of stock value has not moved in 90 days", f"{_money(s['dead_value'], c.cur)} of {_money(value, c.cur)} sits in items with no outward movement for 90 days or more.",
                        metric_key="dead_stock_value", metric_label="Dead stock value", unit="currency", current=s["dead_value"], previous=None, currency=c.cur,
                        source="Bin and Stock Ledger Entry", calculation="stock value of items with a positive balance and no outward movement for 90 days / total stock value",
                        data=[{"label": b["bucket"], "value": b["value"], "unit": "currency"} for b in s["idle_buckets"]], drill={"screen": "inventory", "kind": "slow_moving"}))
    h = s["health"]
    if h.get("score") is not None and h["score"] < 60:
        out.append(make("inventory_health", "alert", "high", "inventory", f"Inventory health is poor ({h['score']}/100)", "The weighted health score is below 60; the factors show what drags it down.",
                        metric_key="inventory_health", metric_label="Inventory health", unit="count", current=h["score"], previous=None, currency=c.cur,
                        source="Inventory health score", calculation="weighted sum of availability, low stock, negative stock, dead stock, overstock and turnover",
                        data=[{"label": f["label"], "value": f["points"], "unit": "points"} for f in h["factors"]], drill={"screen": "inventory"}))
    return out


def rule_inventory_vs_sales(c: Ctx) -> list[dict]:
    v, s = c.kpi("stock_value"), c.kpi("net_sales")
    if not v or not s or v["growth_percent"] is None or s["growth_percent"] is None or not v["previous_value"]:
        return []
    if v["growth_percent"] >= INVENTORY_GROWTH and abs(s["growth_percent"]) <= INVENTORY_FLAT:
        return [make("inventory_vs_sales", "insight", "medium", "inventory", "Inventory value increased while sales stayed flat", f"Stock value rose {_pct(v['growth_percent'])} to {_money(v['value'], c.cur)} while net sales moved {s['growth_percent']:+.1f}%.",
                     metric_key="stock_value", metric_label="Stock value", unit="currency", current=v["value"], previous=v["previous_value"], currency=c.cur,
                     source="Stock Ledger Entry (valuation) and Sales Invoices", calculation="stock value growth of at least 20% with net sales growth within +/-5%",
                     data=[{"label": "Stock value", "value": v["value"], "previous_value": v["previous_value"], "unit": "currency"}, {"label": "Net sales", "value": s["value"], "previous_value": s["previous_value"], "unit": "currency"}],
                     drill={"screen": "inventory"})]
    return []


RULES: list[tuple[str, tuple[str, ...], Callable[[Ctx], list[dict]]]] = [
    ("sales_change", ("sales",), rule_sales_change),
    ("profit", ("gl",), rule_profit),
    ("margin", ("sales",), rule_margin),
    ("expenses", ("gl",), rule_expenses),
    ("category", ("sales",), rule_category_mix),
    ("products", ("sales",), rule_product_movers),
    ("customer", ("sales",), rule_top_customer),
    ("receivables", ("gl",), rule_receivables),
    ("payables", ("gl",), rule_payables),
    ("cash", ("gl",), rule_cash_cover),
    ("inventory", ("stock", "items", "bin"), rule_inventory),
    ("inventory_vs_sales", ("stock", "sales"), rule_inventory_vs_sales),
]


def generate(scope: Scope, today: date | None = None) -> dict[str, Any]:
    today = today or getdate(frappe.utils.today())
    used, note = comparable(scope, today)
    ctx = Ctx(used, today)
    items: list[dict] = []
    skipped: list[str] = []
    for name, kinds, rule in RULES:
        if not _can(*kinds):
            skipped.append(name)
            continue
        try:
            items.extend(rule(ctx))
        except frappe.PermissionError:
            skipped.append(name)
    for it in items:
        it["fingerprint"] = f"{it['id']}|{scope.company}|{it['severity']}|{used.current.from_date}"
    items.sort(key=lambda i: (RANK[i["severity"]], 0 if i["type"] == "alert" else 1, -abs(i["change_percent"] or 0), i["id"]))
    return {
        "currency": scope.currency,
        "generated_for": used.current.as_dict(),
        "compared_with": used.previous.as_dict() if used.previous else None,
        "comparison_note": note,
        "items": items,
        "counts": {
            "by_severity": {s: sum(1 for i in items if i["severity"] == s) for s in SEVERITIES},
            "alerts": sum(1 for i in items if i["type"] == "alert"),
            "insights": sum(1 for i in items if i["type"] == "insight"),
        },
        "skipped_rules": skipped,
    }
