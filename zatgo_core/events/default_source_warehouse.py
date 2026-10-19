"""Fill an empty 'Source Warehouse' (set_warehouse) on Sales Invoice / Sales
Order / Delivery Note, and 'Set Accepted Warehouse' on Purchase Receipt, with
the user's default warehouse (Rejected Warehouse is never defaulted).

The default is the one rule in services/vansalex_settings.py (profile ->
ZG Company Settings -> Stock Settings). It is only used when it belongs to
the document's company; a warehouse the user already chose is never touched.
"""

from __future__ import annotations

import frappe

from zatgo_core.services.vansalex_settings import resolve


def default_source_warehouse(company: str | None = None) -> str | None:
    eff = resolve()
    wh = eff.get("warehouse")
    if not wh:
        return None
    wh_company = frappe.db.get_value("Warehouse", wh, "company")
    if company and wh_company and wh_company != company:
        return None
    return wh


def set_source_warehouse(doc, method=None) -> None:
    if doc.docstatus != 0 or doc.get("set_warehouse"):
        return
    wh = default_source_warehouse(doc.get("company"))
    if wh:
        doc.set_warehouse = wh


@frappe.whitelist()
def get_default_source_warehouse(company: str | None = None) -> str | None:
    return default_source_warehouse(company)


@frappe.whitelist()
def warehouse_query(doctype, txt, searchfield, start, page_len, filters):
    """Link-field search for warehouse fields on the forms above: only
    warehouses ticked "Selectable Warehouse" (plus the user's default),
    or every warehouse when none is ticked yet -- same rule as the VanSaleX
    picker (services/vansalex_settings.py::selectable_warehouses)."""
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    company = filters.get("company")
    cond = "disabled = 0 AND is_group = 0 AND name LIKE %(txt)s"
    params = {"txt": f"%{txt}%", "start": int(start), "page_len": int(page_len), "default": default_source_warehouse(company)}
    if company:
        cond += " AND company = %(company)s"
        params["company"] = company
    flagged = frappe.db.sql(
        f"SELECT 1 FROM `tabWarehouse` WHERE zg_vansalex_selectable = 1 AND disabled = 0"
        f"{' AND company = %(company)s' if company else ''} LIMIT 1",
        params,
    )
    if flagged:
        cond += " AND (zg_vansalex_selectable = 1 OR name = %(default)s)"
    return frappe.db.sql(
        f"SELECT name FROM `tabWarehouse` WHERE {cond} ORDER BY name LIMIT %(page_len)s OFFSET %(start)s",
        params,
    )
