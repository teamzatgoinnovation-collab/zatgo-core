"""VanSaleX purchases — buying stock into the driver's van warehouse.

The mirror of the sales flow (services/vansalex_service.py):

- **Purchase Invoice** (`create_invoice`): a submitted ERPNext Purchase
  Invoice with `update_stock`, so the goods land in the van warehouse at
  once. Cash / Bank / Credit and its account are validated by the same
  `vansalex_settings.resolve_sale` as a sale (a Cash or Bank bill gets its
  Payment Entry (Pay) auto-created on submit by
  services/invoice_cash_payment_service.py, a Credit bill stays payable).
- **Purchase Order** (`create_order`): a submitted Purchase Order, no stock
  impact; `confirm_order` turns it into the Purchase Invoice with ERPNext's
  own `make_purchase_invoice()`.

Every write carries a client_id (`zatgo_client_id`, DB-unique) like a sale.
Field users have no ERPNext permissions on purchase documents; the VanSaleX
module switch (`purchase_invoice` / `purchase_order`, vansalex_access) is the
authorization and the writes run with ignore_permissions, scoped to the
caller's own documents. Rates are the buying price: typed by the driver,
else the item's last purchase rate.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, getdate, today

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login, require_str
from zatgo_core.services.erpnext_writes import _default_company, _parse_items
from zatgo_core.services.van_sale_access import (
    is_vansale_admin,
    is_vansale_user,
    require_own_warehouse,
)
from zatgo_core.services.vansalex_service import _find_by_client_id, insert_idempotent

INVOICE = "Purchase Invoice"
ORDER = "Purchase Order"
KINDS = {"invoice": INVOICE, "order": ORDER}


def require_purchase_user() -> None:
    """Purchases are for VanSale users and admins (their ERPNext role has no
    purchase permissions, so this is checked here, not by Frappe)."""
    require_login()
    if not (is_vansale_admin() or is_vansale_user()):
        frappe.throw("Purchases are for VanSale users.", frappe.PermissionError)


def _supplier(name: str) -> str:
    supplier = require_str(name, "supplier")
    if not frappe.db.exists("Supplier", supplier):
        found = frappe.get_all("Supplier", filters={"supplier_name": supplier}, pluck="name", limit=2)
        if len(found) != 1:
            frappe.throw(f"Supplier not found: {supplier}", frappe.DoesNotExistError)
        supplier = found[0]
    if frappe.db.get_value("Supplier", supplier, "disabled"):
        frappe.throw(f"Supplier {supplier} is disabled.", frappe.ValidationError)
    return supplier


def _buying_price_list() -> str | None:
    return frappe.db.get_single_value("Buying Settings", "buying_price_list") or None


def _buying_rate(item_code: str) -> float:
    """What a line with no typed rate is bought at: the item's last purchase
    rate, else its buying Item Price, else its valuation rate."""
    rate = flt(frappe.db.get_value("Item", item_code, "last_purchase_rate"))
    price_list = _buying_price_list()
    if rate <= 0 and price_list:
        rate = flt(
            frappe.db.get_value(
                "Item Price", {"item_code": item_code, "price_list": price_list, "buying": 1}, "price_list_rate"
            )
        )
    if rate <= 0:
        rate = flt(frappe.db.get_value("Item", item_code, "valuation_rate"))
    return rate


def _rows(items: Any) -> list[dict[str, Any]]:
    """Validated lines, each with a buying rate (typed, else the item's)."""
    if isinstance(items, str):
        import json

        items = json.loads(items)
    normalized = []
    for raw in items or []:
        if isinstance(raw, dict):
            row = dict(raw)
            if row.get("rate") in (None, "", 0) and row.get("unit_price") is not None:
                row["rate"] = row["unit_price"]
            normalized.append(row)
    rows = _parse_items(normalized)
    for row in rows:
        if not frappe.db.exists("Item", row["item_code"]):
            frappe.throw(f"Item not found: {row['item_code']}", frappe.DoesNotExistError)
        if row["rate"] <= 0:
            row["rate"] = _buying_rate(row["item_code"])
        if row["rate"] <= 0:
            frappe.throw(
                f"{row['item_code']}: no buying price on record — enter a rate.", frappe.ValidationError
            )
    return rows


def _apply_purchase_taxes(doc: Any, company: str) -> None:
    template = frappe.db.get_value(
        "Purchase Taxes and Charges Template", {"company": company, "is_default": 1, "disabled": 0}, "name"
    )
    if not template:
        return
    from erpnext.controllers.accounts_controller import get_taxes_and_charges

    doc.taxes_and_charges = template
    doc.set("taxes", [])
    for tax in get_taxes_and_charges("Purchase Taxes and Charges Template", template):
        doc.append("taxes", dict(tax))


def _apply_payment(doc: Any, sale: dict[str, Any]) -> None:
    """Cash / Bank / Credit onto the Purchase Invoice (its Payment Entry is
    created on submit by the existing hook)."""
    if not sale.get("payment_type"):
        return
    meta = frappe.get_meta(INVOICE)
    values = {"custom_payment_type": sale["payment_type"]}
    for key in ("cash_account", "bank_account", "bank_reference_no"):
        if sale.get(key):
            values[f"custom_{key}"] = sale[key]
    for key, value in values.items():
        if meta.has_field(key):
            doc.set(key, value)


def _submit(doc: Any, failure: str) -> None:
    try:
        doc.flags.ignore_permissions = True
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="VanSaleX purchase submit failed", message=frappe.get_traceback())
        frappe.throw(failure, frappe.ValidationError)


def map_purchase(doc: Any) -> dict[str, Any]:
    kind = "order" if doc.doctype == ORDER else "invoice"
    return {
        "name": doc.name,
        "erp_name": doc.name,
        "kind": kind,
        "supplier": doc.supplier,
        "supplier_name": doc.get("supplier_name") or doc.supplier,
        "date": str(doc.get("posting_date") or doc.get("transaction_date") or ""),
        "grand_total": flt(doc.grand_total),
        "rounded_total": flt(doc.rounded_total) or flt(doc.grand_total),
        "outstanding": flt(doc.get("outstanding_amount")),
        "status": doc.status,
        "docstatus": int(doc.docstatus or 0),
        "payment_type": doc.get("custom_payment_type") or "",
        "client_id": doc.get("zatgo_client_id") or "",
        "company": doc.company,
        "warehouse": doc.get("set_warehouse") or "",
        "currency": doc.currency,
        "items": [
            {
                "item_code": i.item_code,
                "item_name": i.item_name,
                "qty": flt(i.qty),
                "rate": flt(i.rate),
                "amount": flt(i.amount),
                "uom": i.uom,
            }
            for i in doc.items
        ],
    }


def _ack(doc: Any, cid: str, *, idempotent: bool, created: bool) -> dict[str, Any]:
    return ok(
        {**map_purchase(doc), "client_id": cid},
        meta={
            "stub": False,
            "idempotent": idempotent,
            "created": created,
            "submitted": int(doc.docstatus or 0) == 1,
            "source": doc.doctype,
        },
    )


def _replay(doctype: str, name: str, cid: str, failure: str) -> dict[str, Any]:
    """The caller's own document for this client_id (a draft left by a
    failed attempt is submitted now)."""
    doc = frappe.get_doc(doctype, name)
    status = int(doc.docstatus or 0)
    if status == 2:
        frappe.throw(
            f"{doctype} {doc.name} was cancelled. Start again with a new client_id.", frappe.ValidationError
        )
    if status == 0:
        _submit(doc, failure)
        doc.reload()
    return _ack(doc, cid, idempotent=True, created=False)


# -- invoice -------------------------------------------------------------------


def create_invoice(
    client_id: str,
    supplier: str,
    items: Any,
    warehouse: str | None = None,
    payment_type: str | None = None,
    cash_account: str | None = None,
    bank_account: str | None = None,
    bank_reference_no: str | None = None,
    supplier_invoice_no: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.vansalex_settings import resolve_sale

    require_purchase_user()
    cid = require_str(client_id, "client_id")
    failure = "Could not create and submit the Purchase Invoice. Check the stock and accounts, then retry."

    existing = _find_by_client_id(INVOICE, cid)
    if existing:
        return _replay(INVOICE, existing, cid, failure)

    party = _supplier(supplier)
    rows = _rows(items)
    sale = resolve_sale(
        payment_type=payment_type,
        warehouse=(warehouse or "").strip(),
        cash_account=cash_account,
        bank_account=bank_account,
        bank_reference_no=bank_reference_no,
    )
    wh = sale["warehouse"]
    company = frappe.db.get_value("Warehouse", wh, "company") or _default_company(None)

    doc = frappe.get_doc(
        {
            "doctype": INVOICE,
            "supplier": party,
            "company": company,
            "posting_date": today(),
            "items": rows,
            "update_stock": 1,
            "set_warehouse": wh,
            "bill_no": (supplier_invoice_no or "").strip()[:140] or None,
            "zatgo_client_id": cid,
        }
    )
    _apply_purchase_taxes(doc, company)
    _apply_payment(doc, sale)
    doc.flags.ignore_permissions = True

    doc, created = insert_idempotent(doc, doctype=INVOICE, client_id=cid)
    if not created:
        return _replay(INVOICE, doc.name, cid, failure)
    _submit(doc, failure)
    doc.reload()
    return _ack(doc, cid, idempotent=False, created=True)


# -- order ---------------------------------------------------------------------


def create_order(client_id: str, supplier: str, items: Any) -> dict[str, Any]:
    """A submitted Purchase Order — nothing is received until it is
    confirmed into an invoice."""
    require_purchase_user()
    cid = require_str(client_id, "client_id")
    failure = "Could not create and submit the Purchase Order. Retry."

    existing = _find_by_client_id(ORDER, cid)
    if existing:
        return _replay(ORDER, existing, cid, failure)

    party = _supplier(supplier)
    rows = _rows(items)
    wh = require_own_warehouse(None)
    if not wh:
        frappe.throw("Van warehouse is required. Set warehouse on ZG Van Sale Profile.", frappe.ValidationError)
    company = frappe.db.get_value("Warehouse", wh, "company") or _default_company(None)
    for row in rows:
        row["warehouse"] = wh
        row["schedule_date"] = today()

    doc = frappe.get_doc(
        {
            "doctype": ORDER,
            "supplier": party,
            "company": company,
            "transaction_date": today(),
            "schedule_date": today(),
            "items": rows,
            "zatgo_client_id": cid,
        }
    )
    _apply_purchase_taxes(doc, company)
    doc.flags.ignore_permissions = True

    doc, created = insert_idempotent(doc, doctype=ORDER, client_id=cid)
    if not created:
        return _replay(ORDER, doc.name, cid, failure)
    _submit(doc, failure)
    doc.reload()
    return _ack(doc, cid, idempotent=False, created=True)


def confirm_order(
    client_id: str,
    purchase_order: str,
    warehouse: str | None = None,
    payment_type: str | None = None,
    cash_account: str | None = None,
    bank_account: str | None = None,
    bank_reference_no: str | None = None,
    supplier_invoice_no: str | None = None,
) -> dict[str, Any]:
    """Receive a submitted Purchase Order: its Purchase Invoice (stock in,
    Cash / Bank / Credit as for `create_invoice`). `client_id` keys the
    resulting invoice."""
    from erpnext.buying.doctype.purchase_order.purchase_order import get_mapped_purchase_invoice

    from zatgo_core.services.vansalex_settings import resolve_sale

    require_purchase_user()
    cid = require_str(client_id, "client_id")
    po_name = require_str(purchase_order, "purchase_order")
    failure = "Could not convert the Purchase Order into a Purchase Invoice. Check the stock and accounts, then retry."

    existing = _find_by_client_id(INVOICE, cid)
    if existing:
        return _replay(INVOICE, existing, cid, failure)

    if not frappe.db.exists(ORDER, po_name):
        frappe.throw(f"Purchase Order not found: {po_name}", frappe.DoesNotExistError)
    po = frappe.get_doc(ORDER, po_name)
    if int(po.docstatus or 0) != 1:
        frappe.throw(f"Purchase Order {po_name} is not submitted.", frappe.ValidationError)
    if not is_vansale_admin() and po.owner != frappe.session.user:
        frappe.throw("Access denied: you can only convert your own orders.", frappe.PermissionError)

    sale = resolve_sale(
        payment_type=payment_type,
        warehouse=(warehouse or "").strip(),
        cash_account=cash_account,
        bank_account=bank_account,
        bank_reference_no=bank_reference_no,
    )
    wh = sale["warehouse"]

    # ERPNext's own mapper (what make_purchase_invoice wraps), without its
    # permission check: field users hold no purchase permissions.
    doc = get_mapped_purchase_invoice(po_name, ignore_permissions=True)
    doc.update_stock = 1
    doc.set_warehouse = wh
    for item in doc.items or []:
        item.warehouse = wh
    if (supplier_invoice_no or "").strip():
        doc.bill_no = supplier_invoice_no.strip()[:140]
    doc.zatgo_client_id = cid
    _apply_payment(doc, sale)
    doc.flags.ignore_permissions = True

    doc, created = insert_idempotent(doc, doctype=INVOICE, client_id=cid)
    if not created:
        return _replay(INVOICE, doc.name, cid, failure)
    _submit(doc, failure)
    doc.reload()
    payload = _ack(doc, cid, idempotent=False, created=True)
    payload["data"]["purchase_order"] = po_name
    return payload


# -- reads ---------------------------------------------------------------------


def list_suppliers(search: str | None = None, limit: int | str = 50) -> list[dict[str, Any]]:
    """Enabled suppliers for the picker (read-only; the module switch is the
    gate, not the Supplier permission field users don't have)."""
    term = (search or "").strip()
    or_filters = [["name", "like", f"%{term}%"], ["supplier_name", "like", f"%{term}%"]] if term else None
    return frappe.get_all(
        "Supplier",
        filters={"disabled": 0},
        or_filters=or_filters,
        fields=["name", "supplier_name", "supplier_group", "mobile_no"],
        order_by="supplier_name asc",
        limit_page_length=min(max(int(limit or 50), 1), 200),
    )


def list_purchases(kind: str, page: int | str = 1, page_size: int | str = 20) -> dict[str, Any]:
    """The caller's own purchase invoices or orders (admins: all), newest first."""
    doctype = KINDS.get((kind or "").strip().lower())
    if not doctype:
        frappe.throw("kind must be 'invoice' or 'order'.")
    require_purchase_user()
    page_i, size_i, start = parse_pagination(page, page_size)
    filters: dict[str, Any] = {"docstatus": ["<", 2]}
    if not is_vansale_admin():
        filters["owner"] = frappe.session.user
    total = frappe.db.count(doctype, filters)
    names = frappe.get_all(
        doctype, filters=filters, pluck="name", order_by="creation desc", start=start, page_length=size_i
    )
    data = [map_purchase(frappe.get_doc(doctype, n)) for n in names]
    payload = paginated(data, page=page_i, page_size=size_i, total=total)
    payload["meta"] = {**payload.get("meta", {}), "source": doctype}
    return payload


def purchase_pdf(kind: str, name: str, print_format: str | None = None) -> dict[str, Any]:
    """The document's PDF (base64), in the site's default print format for
    it (ERPNext's Customize Form setting) unless [print_format] is given.
    Read-only; field users only get their own."""
    import base64

    doctype = KINDS.get((kind or "").strip().lower())
    if not doctype:
        frappe.throw("kind must be 'invoice' or 'order'.")
    require_purchase_user()
    docname = require_str(name, "name")
    if not frappe.db.exists(doctype, docname):
        frappe.throw(f"{doctype} not found: {docname}", frappe.DoesNotExistError)
    owner, docstatus = frappe.db.get_value(doctype, docname, ["owner", "docstatus"])
    if not is_vansale_admin() and owner != frappe.session.user:
        frappe.throw("Access denied: not your document.", frappe.PermissionError)
    if int(docstatus or 0) != 1:
        frappe.throw(f"{doctype} {docname} is not submitted yet.", frappe.ValidationError)
    fmt = (print_format or "").strip() or frappe.get_meta(doctype).default_print_format or None
    if fmt and not frappe.db.exists("Print Format", fmt):
        fmt = None
    doc = frappe.get_doc(doctype, docname)
    doc.flags.ignore_permissions = True
    pdf_bytes = frappe.get_print(doctype, docname, print_format=fmt, as_pdf=True, doc=doc)
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode("utf-8")
    return ok(
        {
            "name": docname,
            "print_format": fmt or "Standard",
            "content_type": "application/pdf",
            "filename": f"{docname}.pdf",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        },
        meta={"source": "vansalex.purchases.pdf"},
    )
