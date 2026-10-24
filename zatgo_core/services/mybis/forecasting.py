"""Forecast data layer: builds the history of a business figure from ERPNext, runs a `forecast` engine over it and returns a payload
in which history, forecast and estimate are never confused.

Subjects (all in company currency): `sales` (net sales), `revenue` (income accounts, ledger), `purchases` (net), `cash_flow` (net
movement of Cash / Bank accounts, with the projected balance) and `customer` (net sales of one customer). `demand` is per item.
The forecast starts after the last complete day (or month) of history; today's partial figures are not used.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, getdate

from zatgo_core.services.mybis import forecast as fc
from zatgo_core.services.mybis import metrics

HORIZONS = {"7d": ("day", 7), "30d": ("day", 30), "90d": ("day", 90), "12m": ("month", 12)}
SUBJECTS = {
    "sales": ("sales", True),
    "customer": ("sales", True),
    "purchases": ("purchases", True),
    "revenue": ("gl", True),
    "cash_flow": ("gl", False),  # (guard key, non-negative?)
}
SUBJECT_LABELS = {"sales": "Net sales", "customer": "Net sales", "purchases": "Net purchases", "revenue": "Revenue (income accounts)", "cash_flow": "Net cash movement"}
METHOD_NOTE = {
    "moving_average": "the average of the most recent periods",
    "weighted_moving_average": "a weighted average of the most recent periods (newer weigh more)",
    "exponential_smoothing": "exponential smoothing of the level",
    "holt": "exponential smoothing of the level and the trend",
}


def guard_kind(subject: str) -> str:
    if subject not in SUBJECTS:
        frappe.throw(_("subject must be one of {0}").format(", ".join(SUBJECTS)), frappe.ValidationError)
    return SUBJECTS[subject][0]


def _bucket_sql(column: str, granularity: str) -> str:
    return column if granularity == "day" else f"DATE_FORMAT({column}, '%%Y-%%m-01')"


def history(company: str, subject: str, start: date, end: date, granularity: str, party: str | None = None) -> dict[date, float]:
    """Figure per day / month between start and end (inclusive); periods with no activity are absent (the caller fills zeros)."""
    params: dict[str, Any] = {"company": company, "start": start, "end": end}
    if subject in ("sales", "customer", "purchases"):
        doc, field = ("Sales Invoice", "customer") if subject != "purchases" else ("Purchase Invoice", "supplier")
        extra = ""
        if subject == "customer":
            if not party:
                frappe.throw(_("party is required for a customer forecast"), frappe.ValidationError)
            params["party"] = party
            extra = f" AND {field} = %(party)s"
        bucket = _bucket_sql("posting_date", granularity)
        rows = frappe.db.sql(
            f"""SELECT {bucket} AS d, COALESCE(SUM(base_net_total), 0) AS v FROM `tab{doc}`
                WHERE docstatus = 1 AND company = %(company)s AND posting_date BETWEEN %(start)s AND %(end)s{extra} GROUP BY d""",
            params,
        )
    else:
        bucket = _bucket_sql("gle.posting_date", granularity)
        if subject == "revenue":
            value = "SUM(CASE WHEN acc.root_type = 'Income' THEN gle.credit - gle.debit END)"
            where = "AND gle.voucher_type != 'Period Closing Voucher'"
        else:
            value = "SUM(CASE WHEN acc.account_type IN ('Cash', 'Bank') THEN gle.debit - gle.credit END)"
            where = ""
        rows = frappe.db.sql(
            f"""SELECT {bucket} AS d, COALESCE({value}, 0) AS v FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
                WHERE gle.company = %(company)s AND gle.is_cancelled = 0 AND gle.posting_date BETWEEN %(start)s AND %(end)s {where} GROUP BY d""",
            params,
        )
    return {getdate(d): flt(v) for d, v in rows}


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _month_add(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, 1)


def _periods(start: date, end: date, granularity: str) -> list[date]:
    if granularity == "day":
        return _days(start, end)
    out, cur = [], start.replace(day=1)
    while cur <= end:
        out.append(cur)
        cur = _month_add(cur, 1)
    return out


def _step(d: date, n: int, granularity: str) -> date:
    return d + timedelta(days=n) if granularity == "day" else _month_add(d, n)


def balance_now(company: str, as_of: date) -> float:
    row = frappe.db.sql(
        """
        SELECT COALESCE(SUM(gle.debit - gle.credit), 0) FROM `tabGL Entry` gle JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.company = %(company)s AND gle.is_cancelled = 0 AND gle.posting_date <= %(as_of)s AND acc.account_type IN ('Cash', 'Bank')
        """,
        {"company": company, "as_of": as_of},
    )
    return flt(row[0][0])


def due_between(company: str, start: date, end: date) -> dict[str, float]:
    """What known open invoices say will fall due in a window (informational: it is not a forecast)."""
    out = {}
    for key, doc in (("receivables_due", "Sales Invoice"), ("payables_due", "Purchase Invoice")):
        row = frappe.db.sql(
            f"""SELECT COALESCE(SUM(outstanding_amount * conversion_rate), 0) FROM `tab{doc}`
                WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0 AND due_date BETWEEN %(start)s AND %(end)s""",
            {"company": company, "start": start, "end": end},
        )
        out[key] = round(flt(row[0][0]), 2)
    return out


def build(company: str, currency: str, subject: str, horizon: str, method: str, party: str | None, today: date) -> dict[str, Any]:
    guard_kind(subject)
    if horizon not in HORIZONS:
        frappe.throw(_("horizon must be one of {0}").format(", ".join(HORIZONS)), frappe.ValidationError)
    if method not in fc.METHODS:
        frappe.throw(_("method must be one of {0}").format(", ".join(fc.METHODS)), frappe.ValidationError)
    granularity, steps = HORIZONS[horizon]
    floor = 0.0 if SUBJECTS[subject][1] else None
    unit = {"day": "day", "month": "month"}[granularity]

    if granularity == "day":
        end = today - timedelta(days=1)
        start = end - timedelta(days=max(120, 3 * steps) - 1 if steps < 90 else 364)
    else:
        end = _month_add(today.replace(day=1), -1)  # last complete month
        start = _month_add(end, -35)
        end = _month_add(end, 1) - timedelta(days=1)  # its last day
    raw = history(company, subject, start, end, granularity, party)
    periods = _periods(start, end, granularity)
    values = [raw.get(p, 0.0) for p in periods]
    first = next((i for i, v in enumerate(values) if v != 0), None)
    notes: list[str] = []
    if first is not None and first > 0:  # all zero: keep the window, the engine will say so
        notes.append(f"History starts at the first {unit} with activity ({periods[first].isoformat()}).")
        periods, values = periods[first:], values[first:]

    min_hist = fc.MIN_HISTORY if granularity == "day" else 6
    base = {
        "subject": subject,
        "subject_label": SUBJECT_LABELS[subject],
        "party": party,
        "currency": currency,
        "horizon": horizon,
        "granularity": granularity,
        "as_of": today.isoformat(),
        "labels": {"history": "Historical (actual)", "forecast": "Forecast (statistical estimate, not AI)"},
    }
    try:
        res = fc.run(
            values,
            steps,
            method=method,
            window=7 if granularity == "day" else 3,
            period=7 if granularity == "day" else 12,
            offset=periods[0].weekday() if granularity == "day" else periods[0].month - 1,
            floor=floor,
            min_history=min_hist,
            cycle_name="week" if granularity == "day" else "year",
        )
    except fc.InsufficientHistory as exc:
        return {**base, "available": False, "reason": f"{exc} Forecasting needs at least {min_hist} {unit}s of history for this figure."}

    first_fc = _step(periods[-1], 1, granularity)
    points = [
        {"date": _step(first_fc, i, granularity).isoformat(), "value": res.values[i], "lower": res.lower[i], "upper": res.upper[i]}
        for i in range(steps)
    ]
    show = {"day": min(len(periods), 60 if steps < 90 else 120), "month": min(len(periods), 24)}[granularity]
    hist = [{"date": p.isoformat(), "value": round(v, 2)} for p, v in list(zip(periods, values))[-show:]]
    prior = values[-steps:]
    fc_total = round(sum(res.values), 2)
    prior_total = round(sum(prior), 2)
    half = (sum(((u - l) / 2) ** 2 for l, u in zip(res.lower, res.upper))) ** 0.5
    summary = {
        "historical_total": prior_total,
        "historical_periods": len(prior),
        "forecast_total": fc_total,
        "forecast_lower": round(max(fc_total - half, 0.0) if floor == 0.0 else fc_total - half, 2),
        "forecast_upper": round(fc_total + half, 2),
        "growth_percent": metrics.metric(fc_total, prior_total)["growth_percent"],
    }
    out = {
        **base,
        "available": True,
        "method": res.method,
        "method_label": res.label,
        "method_params": res.params,
        "method_note": f"Forecast = {METHOD_NOTE[res.method]}"
        + (" with a repeating weekly pattern" if res.seasonal and granularity == "day" else " with a repeating yearly pattern" if res.seasonal else "")
        + ".",
        "candidates": res.candidates,
        "history": hist,
        "forecast": points,
        "summary": summary,
        "quality": {"confidence": res.confidence, "n_history": res.n_history, "backtest_wape": res.wape, "typical_error": res.sigma},
        "seasonality": res.seasonal,
        "limitations": notes + res.limitations,
        "range_note": "The likely range covers about 80% of outcomes if errors keep their recent size.",
    }
    if subject == "cash_flow":
        bal = balance_now(company, today)
        running, path = bal, []
        for p in points:
            running += p["value"]
            path.append({"date": p["date"], "balance": round(running, 2)})
        window_end = _step(first_fc, steps - 1, granularity) if granularity == "day" else _month_add(first_fc, steps) - timedelta(days=1)
        out["cash"] = {
            "balance_now": round(bal, 2),
            "projected_balance": path,
            "projected_end_balance": path[-1]["balance"] if path else round(bal, 2),
            "known_due": due_between(company, today, window_end),
            "note": "Projected balance = today's cash + bank balance plus the forecast net movement. 'Known due' lists open invoices falling due in the window; it is information, not part of the forecast.",
        }
    return out


# -- inventory demand --------------------------------------------------------------------------------------------------


def demand(company: str, horizon_days: int, limit: int, today: date) -> dict[str, Any]:
    """Per stock item: recent sales volume, forecast demand over `horizon_days`, stock and what is already on order.
    Suggested reorder = max(0, forecast demand - stock - on order). Nothing is ordered automatically."""
    horizon_days = max(7, min(int(horizon_days or 30), 90))
    limit = max(1, min(int(limit or 20), 50))
    end = today - timedelta(days=1)
    start = end - timedelta(days=89)
    top = frappe.db.sql(
        """
        SELECT i.item_code, MAX(i.item_name) AS item_name, SUM(i.stock_qty) AS qty, MIN(h.posting_date) AS first_day
        FROM `tabSales Invoice Item` i JOIN `tabSales Invoice` h ON h.name = i.parent JOIN `tabItem` it ON it.name = i.item_code AND it.is_stock_item = 1
        WHERE h.docstatus = 1 AND h.company = %(company)s AND h.posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY i.item_code HAVING qty > 0 ORDER BY qty DESC LIMIT %(limit)s
        """,
        {"company": company, "start": start, "end": end, "limit": limit},
        as_dict=True,
    )
    codes = [r.item_code for r in top]
    series: dict[str, dict[date, float]] = {c: {} for c in codes}
    stock: dict[str, tuple[float, float]] = {}
    if codes:
        for code, d, q in frappe.db.sql(
            """
            SELECT i.item_code, h.posting_date, SUM(i.stock_qty) FROM `tabSales Invoice Item` i JOIN `tabSales Invoice` h ON h.name = i.parent
            WHERE h.docstatus = 1 AND h.company = %(company)s AND h.posting_date BETWEEN %(start)s AND %(end)s AND i.item_code IN %(codes)s
            GROUP BY i.item_code, h.posting_date
            """,
            {"company": company, "start": start, "end": end, "codes": tuple(codes)},
        ):
            series[code][getdate(d)] = flt(q)
        for code, actual, ordered in frappe.db.sql(
            """
            SELECT b.item_code, COALESCE(SUM(b.actual_qty), 0), COALESCE(SUM(b.ordered_qty), 0)
            FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse WHERE w.company = %(company)s AND b.item_code IN %(codes)s GROUP BY b.item_code
            """,
            {"company": company, "codes": tuple(codes)},
        ):
            stock[code] = (flt(actual), flt(ordered))
    rows = []
    for r in top:
        first = getdate(r.first_day)
        days = _days(first, end)
        ys = [series[r.item_code].get(d, 0.0) for d in days]
        span = max(len(days), 14)
        avg_daily = flt(r.qty) / span
        method, confidence, note = "average", "low", "Fewer than 14 days of sales: a simple daily average was used."
        projected = avg_daily * horizon_days
        if len(ys) >= 14:
            try:
                res = fc.run(ys, horizon_days, window=7, period=7, offset=days[0].weekday(), min_history=14)
                projected, method, confidence, note = sum(res.values), res.method, res.confidence, ""
            except fc.InsufficientHistory:
                pass
        actual, ordered = stock.get(r.item_code, (0.0, 0.0))
        rows.append(
            {
                "item_code": r.item_code,
                "item_name": r.item_name or r.item_code,
                "sold_90d": round(flt(r.qty), 3),
                "avg_daily": round(avg_daily, 3),
                "forecast_demand": round(projected, 1),
                "stock": round(actual, 3),
                "on_order": round(ordered, 3),
                "suggested_reorder": round(max(0.0, projected - actual - ordered), 1),
                "days_of_cover": None if avg_daily <= 0 else round(actual / avg_daily, 1),
                "method": method,
                "confidence": confidence,
                "note": note,
            }
        )
    rows.sort(key=lambda x: (-x["suggested_reorder"], -x["forecast_demand"]))
    return {
        "horizon_days": horizon_days,
        "as_of": today.isoformat(),
        "rows": rows,
        "note": "Suggested reorder = forecast demand - stock - already on order. It is a planning figure: no purchase order is created.",
        "labels": {"forecast": "Forecast (statistical estimate, not AI)"},
    }
