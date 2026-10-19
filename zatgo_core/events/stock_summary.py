"""Stock Summary (stock-balance page): Warehouse dropdown lists only
warehouses that currently hold stock (switchable in ZG System Settings),
optionally scoped to a company."""

from __future__ import annotations

import frappe
from frappe.utils import cint


def _live_only() -> bool:
    """ZG System Settings -> 'only warehouses with stock' (default on).
    get_single_value can't tell "never saved" from "unticked" (both 0), so
    read the row: no row yet means the field default, on."""
    rows = frappe.db.sql(
        "SELECT value FROM `tabSingles` WHERE doctype = %s AND field = %s",
        ("ZG System Settings", "stock_summary_live_only"),
    )
    return True if not rows else bool(cint(rows[0][0]))


@frappe.whitelist()
def live_stock_warehouses(doctype, txt, searchfield, start, page_len, filters):
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    params = {"txt": f"%{txt}%", "start": int(start), "page_len": int(page_len)}
    cond = ""
    if filters.get("company"):
        cond = " AND w.company = %(company)s"
        params["company"] = filters["company"]
    if _live_only():
        cond += " AND EXISTS (SELECT 1 FROM `tabBin` b WHERE b.warehouse = w.name AND b.actual_qty != 0)"
    return frappe.db.sql(
        f"""SELECT w.name FROM `tabWarehouse` w
            WHERE w.disabled = 0 AND w.is_group = 0 AND w.name LIKE %(txt)s{cond}
            ORDER BY w.name LIMIT %(page_len)s OFFSET %(start)s""",
        params,
    )
