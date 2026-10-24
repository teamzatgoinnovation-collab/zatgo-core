"""Inventory analytics from ERPNext's own stock tables (Bin = current balance per item and warehouse, Stock Ledger Entry =
movements). Read-only SQL, scoped to the company's warehouses.

Definitions (documented in docs/mybis.md):
- stocked item: an enabled stock Item that has a Bin in a warehouse of the company.
- out of stock: stocked item whose balance over the company's warehouses is exactly 0. Negative: any warehouse balance < 0.
- low stock: a Bin at or below the item's Item Reorder level for that warehouse (levels set > 0).
- slow-moving / dead: balance > 0 and no outward Stock Ledger Entry for 90 days (or ever).
- overstock: balance covers more than 180 days at the last 90 days' outward rate (items that sold nothing are "dead", not overstock).
- idle-days aging: stock value by days since the last outward movement (not FIFO batch aging).
- turnover: outward value of sales / delivery vouchers over 90 days, annualised, over the current stock value.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from zatgo_core.services.mybis import health

DEAD_DAYS = 90
OVERSTOCK_COVER_DAYS = 180
OUTWARD_VOUCHERS = ("Sales Invoice", "Delivery Note", "POS Invoice")

# per-item balance over the company's warehouses
_ITEM_TOTALS = """
    SELECT b.item_code, SUM(b.actual_qty) AS qty, SUM(b.stock_value) AS value
    FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse
    JOIN `tabItem` it ON it.name = b.item_code AND it.is_stock_item = 1 AND it.disabled = 0
    WHERE w.company = %(company)s
    GROUP BY b.item_code
"""

_LAST_OUT = """
    SELECT item_code, MAX(posting_date) AS last_out FROM `tabStock Ledger Entry`
    WHERE company = %(company)s AND actual_qty < 0 AND is_cancelled = 0 GROUP BY item_code
"""

_OUT_90 = """
    SELECT item_code, -SUM(actual_qty) AS out_qty FROM `tabStock Ledger Entry`
    WHERE company = %(company)s AND actual_qty < 0 AND is_cancelled = 0 AND posting_date > %(since)s GROUP BY item_code
"""


def _params(company: str, as_of: date) -> dict[str, Any]:
    return {
        "company": company,
        "as_of": as_of,
        "dead_before": as_of - timedelta(days=DEAD_DAYS),
        "since": as_of - timedelta(days=DEAD_DAYS),
        "vouchers": OUTWARD_VOUCHERS,
    }


def _one(sql: str, params: dict[str, Any]) -> dict[str, Any]:
    rows = frappe.db.sql(sql, params, as_dict=True)
    return rows[0] if rows else {}


def snapshot(company: str) -> dict[str, float]:
    row = _one(
        """
        SELECT COUNT(DISTINCT CASE WHEN b.actual_qty != 0 THEN b.item_code END) AS items,
               COALESCE(SUM(b.actual_qty), 0) AS qty, COALESCE(SUM(b.stock_value), 0) AS value
        FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse WHERE w.company = %(company)s
        """,
        {"company": company},
    )
    return {"items": int(row.get("items") or 0), "qty": flt(row.get("qty")), "value": flt(row.get("value"))}


def counts(company: str, as_of: date) -> dict[str, Any]:
    p = _params(company, as_of)
    stocked = _one(f"SELECT COUNT(*) AS n FROM ({_ITEM_TOTALS}) t", p)
    out = _one(f"SELECT COUNT(*) AS n FROM ({_ITEM_TOTALS}) t WHERE t.qty = 0", p)
    neg = _one(
        """
        SELECT COUNT(DISTINCT b.item_code) AS n FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse
        WHERE w.company = %(company)s AND b.actual_qty < 0
        """,
        p,
    )
    low = _one(
        """
        SELECT COUNT(DISTINCT b.item_code) AS n
        FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse
        JOIN `tabItem Reorder` r ON r.parent = b.item_code AND r.warehouse = b.warehouse
        WHERE w.company = %(company)s AND r.warehouse_reorder_level > 0 AND b.actual_qty <= r.warehouse_reorder_level
        """,
        p,
    )
    dead = _one(
        f"""
        SELECT COUNT(*) AS n, COALESCE(SUM(t.value), 0) AS value
        FROM ({_ITEM_TOTALS}) t LEFT JOIN ({_LAST_OUT}) o ON o.item_code = t.item_code
        WHERE t.qty > 0 AND (o.last_out IS NULL OR o.last_out < %(dead_before)s)
        """,
        p,
    )
    over = _one(
        f"""
        SELECT COUNT(*) AS n, COALESCE(SUM(t.value), 0) AS value
        FROM ({_ITEM_TOTALS}) t JOIN ({_OUT_90}) m ON m.item_code = t.item_code
        WHERE t.qty > 0 AND m.out_qty > 0 AND t.qty / (m.out_qty / {DEAD_DAYS}) > {OVERSTOCK_COVER_DAYS}
        """,
        p,
    )
    outward = _one(
        """
        SELECT COALESCE(-SUM(stock_value_difference), 0) AS v FROM `tabStock Ledger Entry`
        WHERE company = %(company)s AND actual_qty < 0 AND is_cancelled = 0 AND posting_date > %(since)s
          AND voucher_type IN %(vouchers)s
        """,
        p,
    )
    return {
        "stocked_items": int(stocked.get("n") or 0),
        "out_of_stock": int(out.get("n") or 0),
        "negative": int(neg.get("n") or 0),
        "low_stock": int(low.get("n") or 0),
        "dead_items": int(dead.get("n") or 0),
        "dead_value": flt(dead.get("value")),
        "overstock_items": int(over.get("n") or 0),
        "overstock_value": flt(over.get("value")),
        "outward_value_90d": flt(outward.get("v")),
    }


def idle_buckets(company: str, as_of: date) -> list[dict[str, Any]]:
    """Stock value by days since the last outward movement."""
    p = _params(company, as_of)
    rows = frappe.db.sql(
        f"""
        SELECT CASE
                 WHEN o.last_out IS NULL THEN 'never'
                 WHEN DATEDIFF(%(as_of)s, o.last_out) <= 30 THEN '0-30'
                 WHEN DATEDIFF(%(as_of)s, o.last_out) <= 90 THEN '31-90'
                 WHEN DATEDIFF(%(as_of)s, o.last_out) <= 180 THEN '91-180'
                 ELSE '180+' END AS bucket,
               COUNT(*) AS items, COALESCE(SUM(t.value), 0) AS value
        FROM ({_ITEM_TOTALS}) t LEFT JOIN ({_LAST_OUT}) o ON o.item_code = t.item_code
        WHERE t.qty > 0 GROUP BY bucket
        """,
        p,
        as_dict=True,
    )
    by = {r.bucket: r for r in rows}
    return [
        {"bucket": b, "items": int(by[b]["items"]) if b in by else 0, "value": round(flt(by[b]["value"]), 2) if b in by else 0.0}
        for b in ("0-30", "31-90", "91-180", "180+", "never")
    ]


def summary(company: str, as_of: date) -> dict[str, Any]:
    snap = snapshot(company)
    c = counts(company, as_of)
    turnover = None
    if snap["value"] > 0 and c["outward_value_90d"] > 0:
        turnover = round(c["outward_value_90d"] * (365 / DEAD_DAYS) / snap["value"], 2)
    return {
        "as_of": as_of.isoformat(),
        "stock_value": round(snap["value"], 2),
        "stock_qty": round(snap["qty"], 3),
        "items_in_stock": snap["items"],
        "counts": {k: c[k] for k in ("stocked_items", "out_of_stock", "low_stock", "negative", "dead_items", "overstock_items")},
        "dead_value": round(c["dead_value"], 2),
        "overstock_value": round(c["overstock_value"], 2),
        "turnover": turnover,
        "idle_buckets": idle_buckets(company, as_of),
        "health": health.score(
            stocked_items=c["stocked_items"],
            out_of_stock=c["out_of_stock"],
            low_stock=c["low_stock"],
            negative=c["negative"],
            stock_value=snap["value"],
            dead_value=c["dead_value"],
            overstock_value=c["overstock_value"],
            turnover=turnover,
        ),
    }


ALERT_KINDS = ("low_stock", "out_of_stock", "negative", "slow_moving", "overstock", "fast_moving")


def alerts(company: str, as_of: date, kind: str, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    if kind not in ALERT_KINDS:
        frappe.throw(_("kind must be one of {0}").format(", ".join(ALERT_KINDS)), frappe.ValidationError)
    p = {**_params(company, as_of), "limit": int(page_size), "offset": (int(page) - 1) * int(page_size)}
    if kind == "low_stock":
        base = """
            FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse
            JOIN `tabItem Reorder` r ON r.parent = b.item_code AND r.warehouse = b.warehouse
            JOIN `tabItem` it ON it.name = b.item_code AND it.disabled = 0
            WHERE w.company = %(company)s AND r.warehouse_reorder_level > 0 AND b.actual_qty <= r.warehouse_reorder_level
        """
        select = "b.item_code, it.item_name, b.warehouse, b.actual_qty AS qty, b.stock_value AS value, r.warehouse_reorder_level AS level, r.warehouse_reorder_qty AS reorder_qty, NULL AS last_out, NULL AS out_qty"
        order = "(b.actual_qty - r.warehouse_reorder_level) ASC, b.item_code"
    elif kind == "negative":
        base = """
            FROM `tabBin` b JOIN `tabWarehouse` w ON w.name = b.warehouse JOIN `tabItem` it ON it.name = b.item_code
            WHERE w.company = %(company)s AND b.actual_qty < 0
        """
        select = "b.item_code, it.item_name, b.warehouse, b.actual_qty AS qty, b.stock_value AS value, NULL AS level, NULL AS reorder_qty, NULL AS last_out, NULL AS out_qty"
        order = "b.actual_qty ASC, b.item_code"
    else:
        # item-level kinds
        select = "t.item_code, it.item_name, NULL AS warehouse, t.qty, t.value, NULL AS level, NULL AS reorder_qty, o.last_out, m.out_qty"
        join = f"""
            FROM ({_ITEM_TOTALS}) t JOIN `tabItem` it ON it.name = t.item_code
            LEFT JOIN ({_LAST_OUT}) o ON o.item_code = t.item_code LEFT JOIN ({_OUT_90}) m ON m.item_code = t.item_code
        """
        if kind == "out_of_stock":
            base, order = f"{join} WHERE t.qty = 0", "o.last_out DESC, t.item_code"
        elif kind == "slow_moving":
            base = f"{join} WHERE t.qty > 0 AND (o.last_out IS NULL OR o.last_out < %(dead_before)s)"
            order = "t.value DESC, t.item_code"
        elif kind == "overstock":
            base = f"{join} WHERE t.qty > 0 AND m.out_qty > 0 AND t.qty / (m.out_qty / {DEAD_DAYS}) > {OVERSTOCK_COVER_DAYS}"
            order = "t.value DESC, t.item_code"
        else:  # fast_moving: biggest outward quantity in the last 90 days
            base, order = f"{join} WHERE m.out_qty > 0", "m.out_qty DESC, t.item_code"
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM (SELECT 1 {base}) c" if kind in ("low_stock", "negative") else f"SELECT COUNT(*) {base}", p)[0][0] or 0)
    raw = frappe.db.sql(f"SELECT {select} {base} ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s", p, as_dict=True)
    rows = []
    for r in raw:
        idle = (as_of - frappe.utils.getdate(r.last_out)).days if r.last_out else None
        rows.append(
            {
                "item_code": r.item_code,
                "item_name": r.item_name or r.item_code,
                "warehouse": r.warehouse,
                "qty": round(flt(r.qty), 3),
                "value": round(flt(r.value), 2),
                "reorder_level": None if r.level is None else flt(r.level),
                "reorder_qty": None if r.reorder_qty is None else flt(r.reorder_qty),
                "last_outward": None if not r.last_out else str(r.last_out),
                "idle_days": idle,
                "sold_90d": None if r.out_qty is None else round(flt(r.out_qty), 3),
            }
        )
    return rows, total
