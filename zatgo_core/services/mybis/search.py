"""Global search across the records a manager looks for: customers, suppliers, items, invoices, payments, employees, warehouses.

Reads go through `frappe.get_list`, so ERPNext permissions and User Permissions (including the Company restriction) apply to every
hit; a record type the caller may not read is skipped and reported, never searched around the permission. Each hit carries a
`drill` target the app opens with its drill-down router.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

MIN_QUERY = 2

TYPES: dict[str, dict[str, Any]] = {
    "customer": {"doctype": "Customer", "fields": ["name", "customer_name", "customer_group", "disabled"], "search": ["name", "customer_name"], "title": "customer_name", "label": "Customer"},
    "supplier": {"doctype": "Supplier", "fields": ["name", "supplier_name", "supplier_group", "disabled"], "search": ["name", "supplier_name"], "title": "supplier_name", "label": "Supplier"},
    "item": {"doctype": "Item", "fields": ["name", "item_name", "item_group", "stock_uom", "disabled"], "search": ["name", "item_name", "item_code"], "title": "item_name", "label": "Item"},
    "sales_invoice": {
        "doctype": "Sales Invoice",
        "fields": ["name", "customer", "customer_name", "grand_total", "base_grand_total", "posting_date", "status", "is_return", "company"],
        "search": ["name", "customer", "customer_name", "po_no"],
        "title": "name",
        "label": "Sales Invoice",
        "company": True,
    },
    "purchase_invoice": {
        "doctype": "Purchase Invoice",
        "fields": ["name", "supplier", "supplier_name", "grand_total", "base_grand_total", "posting_date", "status", "is_return", "company"],
        "search": ["name", "supplier", "supplier_name", "bill_no"],
        "title": "name",
        "label": "Purchase Invoice",
        "company": True,
    },
    "payment_entry": {
        "doctype": "Payment Entry",
        "fields": ["name", "party", "party_name", "payment_type", "paid_amount", "received_amount", "posting_date", "status", "company", "reference_no"],
        "search": ["name", "party", "party_name", "reference_no"],
        "title": "name",
        "label": "Payment Entry",
        "company": True,
    },
    "employee": {"doctype": "Employee", "fields": ["name", "employee_name", "designation", "department", "status", "company"], "search": ["name", "employee_name"], "title": "employee_name", "label": "Employee", "company": True},
    "warehouse": {"doctype": "Warehouse", "fields": ["name", "warehouse_name", "company", "is_group", "disabled"], "search": ["name", "warehouse_name"], "title": "warehouse_name", "label": "Warehouse", "company": True},
}


def _score(q: str, values: list[str]) -> int:
    ql = q.lower()
    best = 3
    for v in values:
        vl = (v or "").lower()
        if vl == ql:
            return 0
        if vl.startswith(ql):
            best = min(best, 1)
        elif ql in vl:
            best = min(best, 2)
    return best


def _hit(kind: str, r: dict[str, Any]) -> dict[str, Any]:
    cfg = TYPES[kind]
    title = r.get(cfg["title"]) or r["name"]
    base = {"type": kind, "label": cfg["label"], "id": r["name"], "title": title, "subtitle": "", "amount": None, "date": None, "status": None, "is_return": False}
    if kind == "customer":
        base.update(subtitle=" - ".join(x for x in (r["name"] if r["name"] != title else "", r.get("customer_group")) if x), drill={"screen": "customers", "dimension": "customer", "filters": {"customer": r["name"]}, "title": title})
    elif kind == "supplier":
        base.update(subtitle=" - ".join(x for x in (r["name"] if r["name"] != title else "", r.get("supplier_group")) if x), drill={"screen": "suppliers", "dimension": "supplier", "filters": {"supplier": r["name"]}, "title": title})
    elif kind == "item":
        base.update(subtitle=" - ".join(x for x in (r["name"], r.get("item_group")) if x), drill={"screen": "sales", "dimension": "product", "filters": {"product": r["name"]}, "title": title})
    elif kind in ("sales_invoice", "purchase_invoice"):
        party = r.get("customer_name") or r.get("customer") if kind == "sales_invoice" else r.get("supplier_name") or r.get("supplier")
        base.update(subtitle=party or "", amount=flt(r.get("base_grand_total") or r.get("grand_total")), date=str(r.get("posting_date") or ""), status=r.get("status"), is_return=bool(r.get("is_return")),
                    drill={"screen": "sales" if kind == "sales_invoice" else "purchases", "invoice": r["name"]})
    elif kind == "payment_entry":
        amount = r.get("paid_amount") if r.get("payment_type") == "Pay" else r.get("received_amount")
        base.update(subtitle=f"{r.get('payment_type') or ''} - {r.get('party_name') or r.get('party') or ''}".strip(" -"), amount=flt(amount), date=str(r.get("posting_date") or ""), status=r.get("status"), drill={"screen": "record", "type": kind, "id": r["name"]})
    elif kind == "employee":
        base.update(subtitle=" - ".join(x for x in (r.get("designation"), r.get("department")) if x), status=r.get("status"), drill={"screen": "record", "type": kind, "id": r["name"]})
    else:
        base.update(subtitle=r.get("company") or "", drill={"screen": "record", "type": kind, "id": r["name"]})
    return base


def search(q: str, types: list[str] | None, limit: int, company: str | None) -> dict[str, Any]:
    q = (q or "").strip()
    if len(q) < MIN_QUERY:
        frappe.throw(_("Type at least {0} characters to search.").format(MIN_QUERY), frappe.ValidationError)
    wanted = types or list(TYPES)
    bad = [t for t in wanted if t not in TYPES]
    if bad:
        frappe.throw(_("Unknown search type(s): {0}").format(", ".join(bad)), frappe.ValidationError)
    limit = max(1, min(int(limit or 5), 20))
    results: list[dict[str, Any]] = []
    skipped: list[str] = []
    for kind in wanted:
        cfg = TYPES[kind]
        if not frappe.has_permission(cfg["doctype"], "read"):
            skipped.append(kind)
            continue
        filters: dict[str, Any] = {}
        if company and cfg.get("company"):
            filters["company"] = company
        meta = frappe.get_meta(cfg["doctype"])
        fields = [f for f in cfg["fields"] if f == "name" or meta.has_field(f)]
        or_filters = [[cfg["doctype"], f, "like", f"%{q}%"] for f in cfg["search"] if f == "name" or meta.has_field(f)]
        rows = frappe.get_list(cfg["doctype"], fields=fields, filters=filters, or_filters=or_filters, order_by="modified desc", limit_page_length=limit * 4)
        rows = [r for r in rows if not r.get("disabled")]
        rows.sort(key=lambda r: _score(q, [r["name"], str(r.get(cfg["title"]) or "")]))
        results.extend(_hit(kind, r) for r in rows[:limit])
    results.sort(key=lambda h: (_score(q, [h["id"], h["title"]]), wanted.index(h["type"])))
    return {"query": q, "results": results, "skipped": skipped, "counts": {k: sum(1 for h in results if h["type"] == k) for k in wanted}}


# -- record summaries (for hits that have no screen of their own) -----------------------------------------------------

_RECORD_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "payment_entry": [("payment_type", "Type", "text"), ("party_type", "Party type", "text"), ("party_name", "Party", "text"), ("posting_date", "Date", "date"), ("mode_of_payment", "Mode of payment", "text"),
                      ("paid_amount", "Paid amount", "currency"), ("received_amount", "Received amount", "currency"), ("reference_no", "Reference", "text"), ("status", "Status", "text"), ("company", "Company", "text")],
    "employee": [("employee_name", "Name", "text"), ("designation", "Designation", "text"), ("department", "Department", "text"), ("status", "Status", "text"), ("company", "Company", "text"), ("date_of_joining", "Joined", "date")],
    "warehouse": [("warehouse_name", "Name", "text"), ("company", "Company", "text"), ("parent_warehouse", "Parent", "text"), ("warehouse_type", "Type", "text"), ("is_group", "Group", "text")],
}


def record(kind: str, name: str) -> dict[str, Any]:
    from zatgo_core.services import row_scope

    if kind not in _RECORD_FIELDS:
        frappe.throw(_("No summary is available for {0}.").format(kind), frappe.ValidationError)
    cfg = TYPES[kind]
    doc = frappe.get_doc(cfg["doctype"], name)
    doc.check_permission("read")
    if doc.get("company"):
        row_scope.require_company(doc.company)
    meta = frappe.get_meta(cfg["doctype"])
    fields = []
    for fieldname, label, type_ in _RECORD_FIELDS[kind]:
        if not meta.has_field(fieldname):
            continue
        value = doc.get(fieldname)
        if value in (None, "", 0) and type_ != "currency":
            continue
        fields.append({"label": label, "value": str(value) if type_ in ("date", "text") else flt(value), "type": type_})
    if kind == "warehouse":
        row = frappe.db.sql("SELECT COALESCE(SUM(actual_qty), 0), COALESCE(SUM(stock_value), 0) FROM `tabBin` WHERE warehouse = %s", name)[0]
        fields += [{"label": "Stock quantity", "value": flt(row[0]), "type": "number"}, {"label": "Stock value", "value": flt(row[1]), "type": "currency"}]
    currency = frappe.get_cached_value("Company", doc.company, "default_currency") if doc.get("company") else ""
    return {"type": kind, "label": cfg["label"], "id": doc.name, "title": doc.get(cfg["title"]) or doc.name, "currency": currency, "fields": fields}
