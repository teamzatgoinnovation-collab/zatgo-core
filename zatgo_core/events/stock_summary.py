"""Stock Summary (stock-balance page): Warehouse dropdown lists only
warehouses that currently hold stock, optionally scoped to a company."""

from __future__ import annotations

import frappe


@frappe.whitelist()
def live_stock_warehouses(doctype, txt, searchfield, start, page_len, filters):
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    params = {"txt": f"%{txt}%", "start": int(start), "page_len": int(page_len)}
    cond = ""
    if filters.get("company"):
        cond = " AND w.company = %(company)s"
        params["company"] = filters["company"]
    return frappe.db.sql(
        f"""SELECT w.name FROM `tabWarehouse` w
            WHERE w.disabled = 0 AND w.is_group = 0 AND w.name LIKE %(txt)s{cond}
              AND EXISTS (SELECT 1 FROM `tabBin` b WHERE b.warehouse = w.name AND b.actual_qty != 0)
            ORDER BY w.name LIMIT %(page_len)s OFFSET %(start)s""",
        params,
    )
