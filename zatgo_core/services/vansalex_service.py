"""VanSaleX — native ERPNext writes with client_id idempotency."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, getdate, nowdate, today

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login, require_str
from zatgo_core.services.erpnext_reads import map_payment_entry_doc, map_sales_invoice_doc
from zatgo_core.services.erpnext_writes import _apply_return_qtys, _default_company, _parse_items
from zatgo_core.services.idempotency import find_by_client_id as _find_by_client_id
from zatgo_core.services.idempotency import insert_idempotent
from zatgo_core.services.van_sale_access import get_profile, is_vansale_admin, require_own_warehouse


_STATUS_MAP = {
    "planned": "Planned",
    "Planned": "Planned",
    "checkedIn": "Checked In",
    "checked_in": "Checked In",
    "Checked In": "Checked In",
    "completed": "Completed",
    "Completed": "Completed",
    "skipped": "Skipped",
    "Skipped": "Skipped",
}


def _resolve_customer(customer: str) -> str:
    name = require_str(customer, "customer")
    if frappe.db.exists("Customer", name):
        return name
    found = frappe.db.get_value("Customer", {"customer_name": name}, "name")
    if found:
        return found
    frappe.throw(f"Customer not found: {name}")


def _apply_sales_taxes(doc: Any, company: str) -> None:
    from zatgo_core.services.vansalex_settings import sales_tax_template

    template, inclusive = sales_tax_template(company)
    if not template:
        return
    doc.taxes_and_charges = template
    try:
        from erpnext.controllers.accounts_controller import get_taxes_and_charges

        doc.set("taxes", [])
        for tax in get_taxes_and_charges("Sales Taxes and Charges Template", template):
            row = dict(tax)
            # When company prices are tax-inclusive, force included_in_print_rate
            # so ERPNext does not add VAT on top of already-inclusive rates.
            if inclusive:
                row["included_in_print_rate"] = 1
            doc.append("taxes", row)
    except Exception:
        # Older / alternate API
        try:
            doc.append_taxes_from_master()
            if inclusive:
                for tax in doc.taxes or []:
                    tax.included_in_print_rate = 1
        except Exception:
            frappe.log_error(title="VanSale tax template apply failed", message=frappe.get_traceback())


def _ack_sales_invoice(doc: Any, cid: str, *, idempotent: bool, created: bool) -> dict[str, Any]:
    from zatgo_core.setup.ensure_print_formats import PRINT_FORMAT_NAME

    from zatgo_core.services.payment_allocation import payment_details_payload

    return ok(
        {
            **map_sales_invoice_doc(doc),
            "payment_details": payment_details_payload(doc),
            "client_id": cid,
            "erp_name": doc.name,
            "print_format": PRINT_FORMAT_NAME,
            "docstatus": int(doc.docstatus or 0),
        },
        meta={
            "stub": False,
            "idempotent": idempotent,
            "created": created,
            "submitted": int(doc.docstatus or 0) == 1,
            "source": "Sales Invoice",
        },
    )


def _ensure_submitted_sales_invoice(
    doc: Any,
    *,
    warehouse: str | None = None,
) -> Any:
    """Submit draft SI from a prior failed attempt; only succeed when docstatus=1."""
    status = int(doc.docstatus or 0)
    if status == 2:
        frappe.throw(
            f"Sales Invoice {doc.name} was cancelled. Create a new sale with a new client_id.",
            frappe.ValidationError,
        )
    if status == 1:
        return doc

    wh = (warehouse or "").strip()
    if wh:
        if not frappe.db.exists("Warehouse", wh):
            frappe.throw(f"Warehouse not found: {wh}")
        if not doc.set_warehouse:
            doc.update_stock = 1
            doc.set_warehouse = wh
            doc.save()

    if not doc.update_stock or not (doc.set_warehouse or "").strip():
        frappe.throw(
            f"Sales Invoice {doc.name} is still a draft without van warehouse / update_stock. "
            "Set warehouse on the van profile and retry sync.",
            frappe.ValidationError,
        )

    try:
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.throw(
            f"Sales Invoice {doc.name} exists as draft but could not be submitted. "
            "Fix stock/accounts, then retry sync.",
            frappe.ValidationError,
        )
    doc.reload()
    if int(doc.docstatus or 0) != 1:
        frappe.throw(
            f"Sales Invoice {doc.name} is not submitted (docstatus={doc.docstatus}).",
            frappe.ValidationError,
        )
    return doc


def _apply_payment_type(target: Any, sale: dict[str, Any]) -> None:
    """Cash / Bank / Credit onto a Sales Invoice (dict payload or doc). A
    Cash or Bank invoice's Payment Entry is then auto-created on submit, into
    its Cash / Bank account, by the existing zatgo_core hook
    (services/invoice_cash_payment_service.py)."""
    meta = frappe.get_meta("Sales Invoice")
    if not sale.get("payment_type") or not meta.has_field("custom_payment_type"):
        return
    values = {"custom_payment_type": sale["payment_type"]}
    for key in ("cash_account", "bank_account", "bank_reference_no"):
        if sale.get(key) and meta.has_field(f"custom_{key}"):
            values[f"custom_{key}"] = sale[key]
    for key, value in values.items():
        if isinstance(target, dict):
            target[key] = value
        else:
            target.set(key, value)


def _apply_payment_details(doc: Any, payment_details: Any) -> None:
    """Payment split across methods/accounts, recorded on the invoice itself
    as ERPNext POS payments (services/payment_allocation.py). Everything is
    re-validated by the Sales Invoice validate hook; an amount short of the
    total is only accepted for payment_type Credit."""
    from zatgo_core.services.payment_allocation import apply_to_sales_invoice, parse_payment_details
    from zatgo_core.services.vansalex_access import check_payment_rows

    rows = parse_payment_details(payment_details, doc.company)
    # Split / account choice are VanSaleX features the client may not have.
    check_payment_rows(rows, doc.company, "sales_invoice")
    apply_to_sales_invoice(doc, rows)


def _validated_discount_percentage(discount_percentage: Any) -> float:
    pct = flt(discount_percentage or 0)
    if pct < 0 or pct > 100:
        frappe.throw("Discount percentage must be between 0 and 100.", frappe.ValidationError)
    if pct > 0:
        from zatgo_core.services.vansalex_access import require

        require("sales_invoice.discount")
    if pct > 0 and not is_vansale_admin():
        from zatgo_core.services.vansalex_settings import resolve

        cap = flt(resolve()["max_discount_percent"])
        if pct > cap:
            frappe.throw(f"Discount can't exceed {cap:g}% for your account.", frappe.ValidationError)
    return pct


def _line_discounts(items: Any) -> list[float]:
    """Per-line `discount_percentage` from the caller's items, in the same
    order as `_parse_items` returns the rows."""
    if isinstance(items, str):
        import json

        items = json.loads(items)
    if not isinstance(items, list):
        return []
    return [flt(raw.get("discount_percentage") or 0) for raw in items if isinstance(raw, dict)]


def _apply_line_discounts(rows: list[dict[str, Any]], discounts: list[float]) -> None:
    """Discount per item line (VanSaleX `sales_invoice.line_discount`, capped
    by Max Discount %): the line keeps the item's price as its list price
    and carries ERPNext's own discount_percentage / discount_amount, so the
    discount stays visible on the invoice line instead of vanishing into a
    lower rate. Call after rates are final (price list filled in)."""
    if not any(discounts):
        return
    from zatgo_core.services.vansalex_access import require

    require("sales_invoice.line_discount")
    cap = None
    if not is_vansale_admin():
        from zatgo_core.services.vansalex_settings import resolve

        cap = flt(resolve()["max_discount_percent"])
    for row, pct in zip(rows, discounts):
        if not pct:
            continue
        if pct < 0 or pct > 100:
            frappe.throw("Line discount must be between 0 and 100%.", frappe.ValidationError)
        if cap is not None and pct > cap:
            frappe.throw(
                f"Line discount can't exceed {cap:g}% for your account ({row.get('item_code')}).",
                frappe.ValidationError,
            )
        price = flt(row.get("rate"))
        if price <= 0:
            frappe.throw(f"{row.get('item_code')}: no price to discount — enter a rate.", frappe.ValidationError)
        row["price_list_rate"] = price
        row["discount_percentage"] = pct
        row["rate"] = flt(price * (1 - pct / 100), 2)
        row["discount_amount"] = flt(price - row["rate"], 2)


def _build_direct_invoice(
    customer: str,
    items: Any,
    wh: str,
    company: str | None,
    discount_percentage: Any,
    sale: dict[str, Any],
) -> Any:
    """The unsaved Sales Invoice `orders.create` submits -- shared with
    `preview_invoice_totals` so the totals a driver is shown before paying
    are exactly the ones the invoice will get."""
    frappe.has_permission("Sales Invoice", "create", throw=True)
    party = _resolve_customer(customer)
    if isinstance(items, str):
        import json

        items = json.loads(items)
    if isinstance(items, list):
        normalized = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            if row.get("rate") in (None, "", 0) and row.get("unit_price") is not None:
                row["rate"] = row["unit_price"]
            normalized.append(row)
        items = normalized
    rows = _parse_items(items)
    line_discounts = _line_discounts(items)
    pct = _validated_discount_percentage(discount_percentage)

    # The invoice's company is the stock's company — a user-default or
    # "first Company" fallback can disagree with the van warehouse and post
    # to the wrong books (or fail on party-account currency).
    company_name = frappe.db.get_value("Warehouse", wh, "company") or _default_company(company)
    # Prefer customer default price list when item rates missing
    pl = frappe.db.get_value("Customer", party, "default_price_list")
    from zatgo_core.services.vansalex_access import check_item_rates

    check_item_rates(rows, pl)
    if pl:
        for row in rows:
            if flt(row.get("rate") or 0) <= 0:
                rate = frappe.db.get_value(
                    "Item Price",
                    {"item_code": row.get("item_code"), "price_list": pl},
                    "price_list_rate",
                )
                if rate is not None:
                    row["rate"] = flt(rate)
    _apply_line_discounts(rows, line_discounts)

    # No naming_series here: the Sales Invoice before_insert hook picks it from
    # the caller's rule in ZG Sales Invoice Naming Settings (or ERPNext's default).
    doc_payload: dict[str, Any] = {
        "doctype": "Sales Invoice",
        "customer": party,
        "company": company_name,
        "posting_date": today(),
        "items": rows,
        "update_stock": 1,
        "set_warehouse": wh,
    }
    _apply_payment_type(doc_payload, sale)
    if pct > 0:
        # Discount is applied to Net Total (before tax), not Grand Total —
        # ZATCA requires VAT to be computed on the actual discounted
        # taxable value, not subtracted from an already-taxed total.
        doc_payload["apply_discount_on"] = "Net Total"
        doc_payload["additional_discount_percentage"] = pct

    doc = frappe.get_doc(doc_payload)
    if pl and frappe.get_meta("Sales Invoice").has_field("selling_price_list"):
        doc.selling_price_list = pl

    _apply_sales_taxes(doc, company_name)
    return doc


def preview_invoice_totals(
    customer: str,
    items: Any,
    warehouse: str | None = None,
    company: str | None = None,
    discount_percentage: Any = None,
) -> dict[str, Any]:
    """Totals `orders.create` would give this sale, computed by ERPNext's own
    taxes_and_totals without saving anything -- above all `rounded_total`,
    what a split payment has to add up to (the app can't reproduce ERPNext's
    rounding: smallest currency fraction + the site's rounding method)."""
    from zatgo_core.services.vansalex_settings import resolve_sale

    require_login()
    sale = resolve_sale(payment_type=None, warehouse=(warehouse or "").strip())
    doc = _build_direct_invoice(customer, items, sale["warehouse"], company, discount_percentage, sale)
    doc.set_missing_values(for_validate=True)
    doc.calculate_taxes_and_totals()
    grand = flt(doc.grand_total)
    rounded = flt(doc.rounded_total)
    return ok(
        {
            "net_total": flt(doc.net_total),
            "total_taxes_and_charges": flt(doc.total_taxes_and_charges),
            "grand_total": grand,
            "rounded_total": rounded,
            "rounding_adjustment": flt(doc.rounding_adjustment),
            # What payments must add up to (rounded_total is 0 when rounding
            # is disabled).
            "payable_total": rounded or grand,
            "currency": doc.currency,
        }
    )


def create_order(
    client_id: str,
    customer: str,
    items: Any,
    warehouse: str | None = None,
    company: str | None = None,
    trip_id: str | None = None,
    discount_percentage: Any = None,
    payment_type: str | None = None,
    cash_account: str | None = None,
    payment_details: Any = None,
    bank_account: str | None = None,
    bank_reference_no: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.vansalex_settings import resolve_sale
    from zatgo_core.services.zatca_qr import generate_and_store_zatca_qr

    require_login()
    cid = require_str(client_id, "client_id")
    wh = (warehouse or "").strip()

    existing = _find_by_client_id("Sales Invoice", cid)
    if existing:
        doc = frappe.get_doc("Sales Invoice", existing)
        doc = _ensure_submitted_sales_invoice(doc, warehouse=wh or None)
        try:
            generate_and_store_zatca_qr(doc)
            frappe.db.commit()
            doc.reload()
        except Exception:
            frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())
        return _ack_sales_invoice(doc, cid, idempotent=True, created=False)

    # Warehouse / Cash-Bank-Credit / its account, validated against the
    # user's effective VanSaleX settings (see services/vansalex_settings.py).
    sale = resolve_sale(
        payment_type=payment_type,
        warehouse=wh,
        cash_account=cash_account,
        bank_account=bank_account,
        bank_reference_no=bank_reference_no,
    )
    wh = sale["warehouse"]

    doc = _build_direct_invoice(customer, items, wh, company, discount_percentage, sale)
    doc.zatgo_client_id = cid
    _apply_payment_details(doc, payment_details)

    doc, created = insert_idempotent(doc, doctype="Sales Invoice", client_id=cid)
    if not created:
        # A concurrent request with the same client_id won the create race —
        # treat it exactly like the pre-check "already exists" branch above.
        doc = _ensure_submitted_sales_invoice(doc, warehouse=wh or None)
        try:
            generate_and_store_zatca_qr(doc)
            frappe.db.commit()
            doc.reload()
        except Exception:
            frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())
        payload = _ack_sales_invoice(doc, cid, idempotent=True, created=False)
        payload["data"]["trip_id"] = (trip_id or "").strip() or None
        return payload

    try:
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.throw(
            "Could not create and submit Sales Invoice. Fix stock/accounts, then retry sync.",
            frappe.ValidationError,
        )

    try:
        generate_and_store_zatca_qr(doc)
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())

    trip = (trip_id or "").strip()
    if trip and frappe.db.exists("ZG Trip", trip) and frappe.db.has_column("ZG Trip", "sales_invoice"):
        try:
            frappe.db.set_value("ZG Trip", trip, "sales_invoice", doc.name, update_modified=False)
            frappe.db.commit()
        except Exception:
            frappe.log_error(title="VanSale trip-SI link failed", message=frappe.get_traceback())

    doc.reload()
    payload = _ack_sales_invoice(doc, cid, idempotent=False, created=True)
    payload["data"]["trip_id"] = trip or None
    return payload


def _ack_sales_order(doc: Any, cid: str, *, idempotent: bool, created: bool) -> dict[str, Any]:
    return ok(
        {
            "name": doc.name,
            "erp_name": doc.name,
            "client_id": cid,
            "customer": doc.customer,
            "grand_total": float(doc.grand_total or 0),
            # What an invoice confirmed from it must be paid in full by.
            "rounded_total": float(doc.rounded_total or doc.grand_total or 0),
            "docstatus": int(doc.docstatus or 0),
            "status": doc.status,
        },
        meta={
            "stub": False,
            "idempotent": idempotent,
            "created": created,
            "submitted": int(doc.docstatus or 0) == 1,
            "source": "Sales Order",
        },
    )


def _normalize_items(items: Any) -> list[dict[str, Any]]:
    if isinstance(items, str):
        import json

        items = json.loads(items)
    if isinstance(items, list):
        normalized = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            if row.get("rate") in (None, "", 0) and row.get("unit_price") is not None:
                row["rate"] = row["unit_price"]
            normalized.append(row)
        items = normalized
    return _parse_items(items)


def create_sales_order(
    client_id: str,
    customer: str,
    items: Any,
    company: str | None = None,
    trip_id: str | None = None,
    discount_percentage: Any = None,
) -> dict[str, Any]:
    """Create+submit a real ERPNext Sales Order — the "Order" side of the
    Order -> Confirm -> Invoice flow. No stock/warehouse impact and no
    ZATCA QR here; those only apply once the order is confirmed into a
    Sales Invoice (see `confirm_order`). The existing `create_order()`
    (Direct Invoice — order_id-equivalent NULL) is untouched by this."""
    require_login()
    cid = require_str(client_id, "client_id")

    existing = _find_by_client_id("Sales Order", cid)
    if existing:
        doc = frappe.get_doc("Sales Order", existing)
        if int(doc.docstatus or 0) == 0:
            doc.submit()
            frappe.db.commit()
            doc.reload()
        return _ack_sales_order(doc, cid, idempotent=True, created=False)

    frappe.has_permission("Sales Order", "create", throw=True)
    if not is_vansale_admin():
        from zatgo_core.services.vansalex_settings import resolve

        if not resolve()["allow_orders"]:
            frappe.throw(
                "Orders (invoice later) are turned off — create an Invoice instead.",
                frappe.PermissionError,
            )
    party = _resolve_customer(customer)
    rows = _normalize_items(items)
    line_discounts = _line_discounts(items)
    from zatgo_core.services.vansalex_access import check_item_rates

    check_item_rates(rows, frappe.db.get_value("Customer", party, "default_price_list"))
    pct = _validated_discount_percentage(discount_percentage)

    # ERPNext's Sales Order controller requires a source warehouse on every
    # stock-item line unconditionally, even though nothing ships until this
    # order is later confirmed into an Invoice (Sales Order submission never
    # touches the Stock Ledger). Without this, create_sales_order() throws
    # "Source warehouse required" for any real stock item — resolve the
    # caller's own van (the same one confirm_order() requires later) purely
    # to satisfy that schema rule.
    wh = require_own_warehouse(None)
    if not wh:
        frappe.throw(
            "Van warehouse is required. Set warehouse on ZG Van Sale Profile.",
            frappe.ValidationError,
        )
    for row in rows:
        row.setdefault("warehouse", wh)

    company_name = frappe.db.get_value("Warehouse", wh, "company") or _default_company(company)
    pl = frappe.db.get_value("Customer", party, "default_price_list")
    if pl:
        for row in rows:
            if flt(row.get("rate") or 0) <= 0:
                rate = frappe.db.get_value(
                    "Item Price",
                    {"item_code": row.get("item_code"), "price_list": pl},
                    "price_list_rate",
                )
                if rate is not None:
                    row["rate"] = flt(rate)
    _apply_line_discounts(rows, line_discounts)

    doc_payload: dict[str, Any] = {
        "doctype": "Sales Order",
        "customer": party,
        "company": company_name,
        "transaction_date": today(),
        "items": rows,
        "zatgo_client_id": cid,
        # Van sales don't go through a formal Delivery Note step —
        # without this, ERPNext's validate_delivery_date() throws
        # "Please enter Delivery Date" on every order.
        "skip_delivery_note": 1,
    }
    if pct > 0:
        # Set on the Sales Order itself so it carries through automatically
        # when confirm_order() later maps it into a Sales Invoice via
        # ERPNext's own make_sales_invoice() (mapped-doctype fields copy).
        doc_payload["apply_discount_on"] = "Net Total"
        doc_payload["additional_discount_percentage"] = pct
    doc = frappe.get_doc(doc_payload)
    if pl and frappe.get_meta("Sales Order").has_field("selling_price_list"):
        doc.selling_price_list = pl

    _apply_sales_taxes(doc, company_name)

    doc, created = insert_idempotent(doc, doctype="Sales Order", client_id=cid)
    if not created:
        if int(doc.docstatus or 0) == 0:
            doc.submit()
            frappe.db.commit()
            doc.reload()
        payload = _ack_sales_order(doc, cid, idempotent=True, created=False)
        payload["data"]["trip_id"] = (trip_id or "").strip() or None
        return payload

    try:
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.throw(
            "Could not create and submit Sales Order. Fix stock/accounts, then retry sync.",
            frappe.ValidationError,
        )

    doc.reload()
    payload = _ack_sales_order(doc, cid, idempotent=False, created=True)
    payload["data"]["trip_id"] = (trip_id or "").strip() or None
    return payload


def confirm_order(
    client_id: str,
    sales_order: str,
    warehouse: str | None = None,
    company: str | None = None,
    trip_id: str | None = None,
    payment_type: str | None = None,
    cash_account: str | None = None,
    payment_details: Any = None,
    bank_account: str | None = None,
    bank_reference_no: str | None = None,
) -> dict[str, Any]:
    """Convert a submitted Sales Order into a submitted Sales Invoice —
    the "Confirm Order" action. `client_id` here is the idempotency key
    for the *resulting Invoice* (a double-tap/retry on Confirm must not
    create two invoices), distinct from the Sales Order's own client_id.
    Uses ERPNext's own `make_sales_invoice()`, which already links
    `Sales Invoice Item.sales_order` back to the source order — no custom
    field needed for that traceability."""
    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

    from zatgo_core.services.vansalex_settings import resolve_sale
    from zatgo_core.services.zatca_qr import generate_and_store_zatca_qr

    require_login()
    cid = require_str(client_id, "client_id")
    wh = (warehouse or "").strip()
    so_name = require_str(sales_order, "sales_order")

    existing = _find_by_client_id("Sales Invoice", cid)
    if existing:
        doc = frappe.get_doc("Sales Invoice", existing)
        doc = _ensure_submitted_sales_invoice(doc, warehouse=wh)
        try:
            generate_and_store_zatca_qr(doc)
            frappe.db.commit()
            doc.reload()
        except Exception:
            frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())
        return _ack_sales_invoice(doc, cid, idempotent=True, created=False)

    if not frappe.db.exists("Sales Order", so_name):
        frappe.throw(f"Sales Order not found: {so_name}")
    sale = resolve_sale(
        payment_type=payment_type,
        warehouse=wh,
        cash_account=cash_account,
        bank_account=bank_account,
        bank_reference_no=bank_reference_no,
    )
    wh = sale["warehouse"]
    so = frappe.get_doc("Sales Order", so_name)
    if int(so.docstatus or 0) != 1:
        frappe.throw(f"Sales Order {so_name} is not submitted.", frappe.ValidationError)
    # A field user may only invoice their own orders (from their own stock).
    if not is_vansale_admin() and so.owner != frappe.session.user:
        frappe.throw(
            "Access denied: you can only convert your own orders.", frappe.PermissionError
        )

    frappe.has_permission("Sales Invoice", "create", throw=True)

    doc = make_sales_invoice(so_name)
    doc.update_stock = 1
    doc.set_warehouse = wh
    # make_sales_invoice() copies each line's warehouse from the Sales
    # Order (defaulted to the company's default warehouse at order-creation
    # time, since the order itself never touches stock/warehouse) —
    # set_warehouse alone only fills a *missing* item warehouse, it doesn't
    # override one already populated by the mapped-doctype copy. Force
    # every line to the van's own warehouse explicitly.
    for item in doc.items or []:
        item.warehouse = wh
    _apply_payment_type(doc, sale)
    _apply_payment_details(doc, payment_details)
    doc.zatgo_client_id = cid

    doc, created = insert_idempotent(doc, doctype="Sales Invoice", client_id=cid)
    if not created:
        doc = _ensure_submitted_sales_invoice(doc, warehouse=wh)
        try:
            generate_and_store_zatca_qr(doc)
            frappe.db.commit()
            doc.reload()
        except Exception:
            frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())
        payload = _ack_sales_invoice(doc, cid, idempotent=True, created=False)
        payload["data"]["trip_id"] = (trip_id or "").strip() or None
        return payload

    try:
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.throw(
            "Could not confirm Sales Order into Sales Invoice. Fix stock/accounts, then retry sync.",
            frappe.ValidationError,
        )

    try:
        generate_and_store_zatca_qr(doc)
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())

    trip = (trip_id or "").strip()
    if trip and frappe.db.exists("ZG Trip", trip) and frappe.db.has_column("ZG Trip", "sales_invoice"):
        try:
            frappe.db.set_value("ZG Trip", trip, "sales_invoice", doc.name, update_modified=False)
            frappe.db.commit()
        except Exception:
            frappe.log_error(title="VanSale trip-SI link failed", message=frappe.get_traceback())

    doc.reload()
    payload = _ack_sales_invoice(doc, cid, idempotent=False, created=True)
    payload["data"]["trip_id"] = trip or None
    payload["data"]["sales_order"] = so_name
    return payload


def _returnable_original(original_name: str) -> Any:
    """The submitted, non-return Sales Invoice [original_name], if the
    caller may return against it: admins any; a field user only their own
    sales or sales from their van's warehouse."""
    if not frappe.db.exists("Sales Invoice", original_name):
        frappe.throw(f"Sales Invoice not found: {original_name}")
    original = frappe.get_doc("Sales Invoice", original_name)
    if int(original.docstatus or 0) != 1:
        frappe.throw(f"Sales Invoice {original_name} is not submitted.", frappe.ValidationError)
    if int(getattr(original, "is_return", 0) or 0):
        frappe.throw(f"Sales Invoice {original_name} is itself a return.", frappe.ValidationError)
    if not is_vansale_admin():
        from zatgo_core.services.vansalex_settings import resolve

        own_wh = resolve().get("warehouse")
        if original.owner != frappe.session.user and not (
            own_wh and (original.set_warehouse or "") == own_wh
        ):
            frappe.throw(
                "Access denied: you can only return items against your own van's sales.",
                frappe.PermissionError,
            )
    return original


def returnable_lines(original: Any) -> list[dict[str, Any]]:
    """Per item of [original]: sold qty, qty already returned by submitted
    credit notes, and what is left to return."""
    sold: dict[str, dict[str, Any]] = {}
    for row in original.items or []:
        line = sold.setdefault(
            row.item_code,
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "uom": row.uom,
                "rate": flt(row.rate),
                "sold_qty": 0.0,
            },
        )
        line["sold_qty"] += flt(row.qty)
    returned: dict[str, float] = {}
    for r in frappe.get_all(
        "Sales Invoice Item",
        filters={
            "parent": ["in", frappe.get_all(
                "Sales Invoice",
                filters={"return_against": original.name, "is_return": 1, "docstatus": 1},
                pluck="name",
            ) or [""]],
        },
        fields=["item_code", "qty"],
    ):
        returned[r.item_code] = returned.get(r.item_code, 0) + abs(flt(r.qty))
    out = []
    for code, line in sold.items():
        line["returned_qty"] = returned.get(code, 0.0)
        line["returnable_qty"] = max(line["sold_qty"] - line["returned_qty"], 0.0)
        out.append(line)
    return out


def get_returnable(sales_invoice: str) -> dict[str, Any]:
    """What can still be returned against [sales_invoice] (for the app's
    New Return screen)."""
    original = _returnable_original(require_str(sales_invoice, "sales_invoice"))
    return {
        "name": original.name,
        "customer": original.customer,
        "customer_name": original.customer_name,
        "posting_date": str(original.posting_date or ""),
        "grand_total": flt(original.grand_total),
        "items": returnable_lines(original),
    }


def create_sales_return(
    client_id: str,
    return_against: str,
    items: Any,
    warehouse: str | None = None,
    company: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Partial/full Sales Return (credit-note Sales Invoice) against a submitted sale."""
    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    from zatgo_core.services.zatca_qr import generate_and_store_zatca_qr

    require_login()
    cid = require_str(client_id, "client_id")

    existing = _find_by_client_id("Sales Invoice", cid)
    if existing:
        doc = frappe.get_doc("Sales Invoice", existing)
        try:
            generate_and_store_zatca_qr(doc)
            frappe.db.commit()
            doc.reload()
        except Exception:
            frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())
        return _ack_sales_invoice(doc, cid, idempotent=True, created=False)

    original_name = require_str(return_against, "return_against")
    original = _returnable_original(original_name)
    # Stock goes back into the caller's van (their default warehouse unless
    # VanSaleX Settings let them pick another of the company's).
    from zatgo_core.services.vansalex_settings import allowed_warehouse

    wh = allowed_warehouse(warehouse)
    if frappe.db.get_value("Warehouse", wh, "company") != original.company:
        frappe.throw(
            f"Warehouse {wh} belongs to another company than {original_name}.",
            frappe.ValidationError,
        )

    frappe.has_permission("Sales Invoice", "create", throw=True)
    if isinstance(items, str):
        import json

        items = json.loads(items)
    if not isinstance(items, list) or not items:
        frappe.throw("At least one line item is required")

    returnable = {r["item_code"]: r for r in returnable_lines(original)}
    requested_qty_by_item: dict[str, float] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        code = require_str(raw.get("item_code") or raw.get("item"), "item_code")
        qty = flt(raw.get("qty") or 0)
        if qty <= 0:
            frappe.throw("Return qty must be greater than zero")
        if code not in returnable:
            frappe.throw(f"Item {code} was not sold on {original_name}")
        requested_qty_by_item[code] = requested_qty_by_item.get(code, 0) + qty
    for code, qty in requested_qty_by_item.items():
        left = returnable[code]["returnable_qty"]
        if qty > left + 1e-6:
            frappe.throw(
                f"Cannot return {qty:g} of {code} — only {left:g} of the "
                f"{returnable[code]['sold_qty']:g} sold on {original_name} is left to return.",
                frappe.ValidationError,
            )

    doc = make_return_doc("Sales Invoice", original_name)
    _apply_return_qtys(doc, requested_qty_by_item, original_name)
    doc.update_stock = 1
    doc.set_warehouse = wh
    doc.zatgo_client_id = cid
    if reason:
        doc.remarks = (f"{doc.remarks}\n" if doc.remarks else "") + f"Return reason: {reason}"

    # naming_series is left to the Sales Invoice before_insert hook
    # (events/sales_invoice_naming.py): the caller's return series from ZG Sales
    # Invoice Naming Settings, else the site's configured "-RET-" counterpart.
    # Never the original's number: the return is a new document in its own series.

    doc.run_method("calculate_taxes_and_totals")
    doc, created = insert_idempotent(doc, doctype="Sales Invoice", client_id=cid)
    if not created:
        try:
            generate_and_store_zatca_qr(doc)
            frappe.db.commit()
            doc.reload()
        except Exception:
            frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())
        return _ack_sales_invoice(doc, cid, idempotent=True, created=False)

    try:
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.throw(
            "Could not create and submit Sales Return. Fix stock/accounts, then retry sync.",
            frappe.ValidationError,
        )

    try:
        generate_and_store_zatca_qr(doc)
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="VanSale ZATCA QR generation failed", message=frappe.get_traceback())

    doc.reload()
    return _ack_sales_invoice(doc, cid, idempotent=False, created=True)


def create_collection(
    client_id: str,
    customer: str,
    amount: float | str,
    method: str | None = None,
    sales_invoice: str | None = None,
    posting_date: str | None = None,
    reference: str | None = None,
    notes: str | None = None,
    payment_details: Any = None,
) -> dict[str, Any]:
    from zatgo_core.services.payment_allocation import (
        apply_to_payment_entry,
        parse_payment_details,
    )

    require_login()
    cid = require_str(client_id, "client_id")
    existing = _find_by_client_id("Payment Entry", cid)
    if existing:
        pe = frappe.get_doc("Payment Entry", existing)
        return ok(
            {**_collection_payload(pe), "client_id": cid, "erp_name": pe.name},
            meta={"stub": False, "idempotent": True, "source": "Payment Entry"},
        )

    frappe.has_permission("Payment Entry", "create", throw=True)
    party = _resolve_customer(customer)
    if not is_vansale_admin():
        from zatgo_core.services.van_sale_access import field_user_customers
        from zatgo_core.services.vansalex_settings import resolve

        # VanSaleX Settings / the driver's profile decide whether collections
        # are limited to the driver's own customers: their route (ZG Trip)
        # plus anyone they invoiced — the same set whose balances the app
        # shows them (aging is scoped the same way).
        if resolve()["restrict_collections_to_route"] and party not in field_user_customers():
            frappe.throw(
                "Access denied: you can only collect from customers on your route "
                "or that you invoiced. Ask your admin to add this customer to your "
                "route, or to turn off 'Restrict Collections to Route' in VanSaleX.",
                frappe.PermissionError,
            )
    # Accounts left blank are filled from the Payment Entry's own company
    # (apply_to_payment_entry), once it is known.
    detail_rows = parse_payment_details(payment_details)
    # Card / split collection are VanSaleX features the client may not have.
    from zatgo_core.services.vansalex_access import check_collection_method, check_payment_rows

    check_payment_rows(detail_rows, "", "collections")
    check_collection_method(method)
    paid = flt(amount)
    if detail_rows:
        rows_total = sum(r["amount"] for r in detail_rows)
        if amount not in (None, "") and abs(paid - rows_total) > 0.005:
            frappe.throw(
                f"amount {paid} does not match the payment_details total {rows_total}."
            )
        paid = rows_total
    if paid <= 0:
        frappe.throw("Payment amount must be greater than zero")

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    si_name = (sales_invoice or "").strip()
    if si_name:
        # Caller explicitly targeted one invoice — single-reference payment
        # against exactly that invoice. It must be an open invoice of the
        # customer that passed the access check above; otherwise the payment
        # would post against a different customer's receivable.
        si = frappe.db.get_value(
            "Sales Invoice", si_name, ["customer", "docstatus", "outstanding_amount"], as_dict=True
        )
        if not si:
            frappe.throw(f"Sales Invoice {si_name} not found")
        if si.customer != party:
            frappe.throw(
                f"Sales Invoice {si_name} belongs to a different customer.",
                frappe.PermissionError,
            )
        if int(si.docstatus or 0) != 1 or flt(si.outstanding_amount) <= 0:
            frappe.throw(f"Sales Invoice {si_name} has nothing outstanding.")
        pe = get_payment_entry("Sales Invoice", si_name, party_amount=paid)
    else:
        # No specific invoice named (the only path the Flutter app actually
        # uses today) — allocate oldest-first across every open invoice
        # until `paid` is exhausted, so a driver can collect a customer's
        # full displayed outstanding in one action even when it spans
        # multiple invoices. This used to target only the single most
        # recently posted invoice, which silently misallocated or hard-
        # rejected any amount larger than that one invoice's outstanding
        # (QA audit BUG-003).
        open_invoices = frappe.get_all(
            "Sales Invoice",
            filters={
                "customer": party,
                "docstatus": 1,
                "outstanding_amount": [">", 0],
            },
            fields=["name", "grand_total", "outstanding_amount", "due_date"],
            order_by="posting_date asc, creation asc",
        )
        if not open_invoices:
            frappe.throw(f"No outstanding Sales Invoice for customer {party}")

        remaining = paid
        allocations: list[tuple[Any, float]] = []
        for inv in open_invoices:
            if remaining <= 0:
                break
            alloc = min(remaining, flt(inv.outstanding_amount))
            allocations.append((inv, alloc))
            remaining -= alloc

        first_inv, first_alloc = allocations[0]
        # get_payment_entry with no party_amount builds exactly one
        # reference row, allocated to first_inv's full outstanding, and
        # resolves all the party/account/currency setup we still want —
        # only the allocation for a partial-against-the-oldest-invoice
        # payment needs correcting down to what's actually being paid.
        pe = get_payment_entry("Sales Invoice", first_inv.name)
        pe.references[0].allocated_amount = first_alloc

        for inv, alloc in allocations[1:]:
            pe.append(
                "references",
                {
                    "reference_doctype": "Sales Invoice",
                    "reference_name": inv.name,
                    "due_date": inv.due_date,
                    "total_amount": inv.grand_total,
                    "outstanding_amount": inv.outstanding_amount,
                    "allocated_amount": alloc,
                },
            )
        # The driver's actual collected amount, not get_payment_entry's
        # single-invoice default — any amount beyond what open_invoices
        # could absorb becomes a normal unallocated advance, computed by
        # Payment Entry's own validate().
        pe.paid_amount = paid
        pe.received_amount = paid

    pe.posting_date = getdate(posting_date) if posting_date else getdate(nowdate())
    if method:
        pe.mode_of_payment = method
    ref = (reference or "").strip()
    pe.reference_no = ref or cid
    pe.reference_date = pe.posting_date
    note = (notes or "").strip()
    if note:
        # Payment Entry's own validate() rebuilds `remarks` from scratch
        # (set_remarks()) unless custom_remarks is set — call it first so
        # our appended note doesn't get silently wiped on insert/submit.
        pe.set_remarks()
        pe.remarks = f"{pe.remarks}\n{note}" if pe.remarks else note
        pe.custom_remarks = 1
    apply_to_payment_entry(pe, detail_rows)
    if frappe.db.has_column("Payment Entry", "zatgo_client_id"):
        pe.zatgo_client_id = cid
    pe, created = insert_idempotent(pe, doctype="Payment Entry", client_id=cid)
    if not created:
        return ok(
            {**_collection_payload(pe), "client_id": cid, "erp_name": pe.name},
            meta={"stub": False, "idempotent": True, "source": "Payment Entry"},
        )
    pe.submit()
    frappe.db.commit()
    return ok(
        {**_collection_payload(pe), "client_id": cid, "erp_name": pe.name},
        meta={"stub": False, "created": True, "submitted": True, "source": "Payment Entry"},
    )


def _collection_payload(pe: Any) -> dict[str, Any]:
    from zatgo_core.services.payment_allocation import payment_details_payload

    return {**map_payment_entry_doc(pe), "payment_details": payment_details_payload(pe)}


def list_van_stock(
    warehouse: str,
    page: int | str = 1,
    page_size: int | str = 100,
) -> dict[str, Any]:
    require_login()
    wh = require_str(warehouse, "warehouse")
    if not frappe.db.exists("Warehouse", wh):
        frappe.throw(f"Warehouse not found: {wh}")
    page_i, size_i, start = parse_pagination(page, page_size)
    filt = {"warehouse": wh, "actual_qty": [">", 0]}
    total = frappe.db.count("Bin", filt)
    rows = frappe.get_all(
        "Bin",
        filters=filt,
        fields=["item_code", "warehouse", "actual_qty", "stock_uom", "valuation_rate"],
        order_by="item_code asc",
        start=start,
        page_length=size_i,
    )
    data = []
    for r in rows:
        item_name = frappe.db.get_value("Item", r.item_code, "item_name") or r.item_code
        std_rate = flt(frappe.db.get_value("Item", r.item_code, "standard_rate") or 0)
        rate = std_rate or flt(r.valuation_rate or 0)
        data.append(
            {
                "id": f"{r.item_code}@{r.warehouse}",
                "item_code": r.item_code,
                "item_name": item_name,
                "warehouse": r.warehouse,
                "qty": float(r.actual_qty or 0),
                "uom": r.stock_uom,
                "unit_price": rate,
                "rate": rate,
            }
        )
    payload = paginated(data, page=page_i, page_size=size_i, total=total, sort="item_code asc")
    payload["meta"] = {**payload.get("meta", {}), "stub": False, "source": "Bin", "warehouse": wh}
    return payload


def adjust_stock(
    client_id: str,
    item_code: str,
    delta: float | str,
    warehouse: str,
    company: str | None = None,
) -> dict[str, Any]:
    require_login()
    cid = require_str(client_id, "client_id")
    existing = _find_by_client_id("Stock Entry", cid)
    if existing:
        se = frappe.get_doc("Stock Entry", existing)
        return ok(
            {
                "name": se.name,
                "erp_name": se.name,
                "client_id": cid,
                "item_code": item_code,
                "delta": flt(delta),
            },
            meta={"stub": False, "idempotent": True, "source": "Stock Entry"},
        )

    frappe.has_permission("Stock Entry", "create", throw=True)
    code = require_str(item_code, "item_code")
    wh = require_str(warehouse, "warehouse")
    qty = flt(delta)
    if qty == 0:
        frappe.throw("delta must not be zero")
    if not frappe.db.exists("Item", code):
        frappe.throw(f"Item not found: {code}")
    if not frappe.db.exists("Warehouse", wh):
        frappe.throw(f"Warehouse not found: {wh}")

    purpose = "Material Receipt" if qty > 0 else "Material Issue"
    abs_qty = abs(qty)
    row: dict[str, Any] = {
        "item_code": code,
        "qty": abs_qty,
    }
    if qty > 0:
        row["t_warehouse"] = wh
    else:
        row["s_warehouse"] = wh

    se = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": purpose,
            "purpose": purpose,
            "company": _default_company(company),
            "items": [row],
            "zatgo_client_id": cid,
        }
    )
    se, created = insert_idempotent(se, doctype="Stock Entry", client_id=cid)
    if not created:
        return ok(
            {
                "name": se.name,
                "erp_name": se.name,
                "client_id": cid,
                "item_code": item_code,
                "delta": flt(delta),
            },
            meta={"stub": False, "idempotent": True, "source": "Stock Entry"},
        )
    se.submit()
    frappe.db.commit()
    return ok(
        {
            "name": se.name,
            "erp_name": se.name,
            "client_id": cid,
            "item_code": code,
            "delta": qty,
            "warehouse": wh,
        },
        meta={"stub": False, "created": True, "submitted": True, "source": "Stock Entry"},
    )


def transfer_stock(
    client_id: str,
    item_code: str,
    qty: float | str,
    from_warehouse: str,
    to_warehouse: str,
    company: str | None = None,
) -> dict[str, Any]:
    """Material Transfer between warehouses (e.g. main WH → van WH)."""
    require_login()
    cid = require_str(client_id, "client_id")
    existing = _find_by_client_id("Stock Entry", cid)
    if existing:
        se = frappe.get_doc("Stock Entry", existing)
        return ok(
            {
                "name": se.name,
                "erp_name": se.name,
                "client_id": cid,
                "item_code": item_code,
                "qty": flt(qty),
                "from_warehouse": from_warehouse,
                "to_warehouse": to_warehouse,
            },
            meta={"stub": False, "idempotent": True, "source": "Stock Entry"},
        )

    frappe.has_permission("Stock Entry", "create", throw=True)
    code = require_str(item_code, "item_code")
    src = require_str(from_warehouse, "from_warehouse")
    dst = require_str(to_warehouse, "to_warehouse")
    amount = flt(qty)
    if amount <= 0:
        frappe.throw("qty must be greater than zero")
    if src == dst:
        frappe.throw("from_warehouse and to_warehouse must differ")
    if not frappe.db.exists("Item", code):
        frappe.throw(f"Item not found: {code}")
    if not frappe.db.exists("Warehouse", src):
        frappe.throw(f"Warehouse not found: {src}")
    if not frappe.db.exists("Warehouse", dst):
        frappe.throw(f"Warehouse not found: {dst}")

    se = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Transfer",
            "purpose": "Material Transfer",
            "company": _default_company(company),
            "items": [
                {
                    "item_code": code,
                    "qty": amount,
                    "s_warehouse": src,
                    "t_warehouse": dst,
                }
            ],
            "zatgo_client_id": cid,
        }
    )
    se, created = insert_idempotent(se, doctype="Stock Entry", client_id=cid)
    if not created:
        return ok(
            {
                "name": se.name,
                "erp_name": se.name,
                "client_id": cid,
                "item_code": item_code,
                "qty": flt(qty),
                "from_warehouse": from_warehouse,
                "to_warehouse": to_warehouse,
            },
            meta={"stub": False, "idempotent": True, "source": "Stock Entry"},
        )
    se.submit()
    frappe.db.commit()
    return ok(
        {
            "name": se.name,
            "erp_name": se.name,
            "client_id": cid,
            "item_code": code,
            "qty": amount,
            "from_warehouse": src,
            "to_warehouse": dst,
        },
        meta={"stub": False, "created": True, "submitted": True, "source": "Stock Entry"},
    )


def update_visit(
    client_id: str,
    stop_id: str,
    visit_status: str,
    lat: float | str | None = None,
    lng: float | str | None = None,
    notes: str | None = None,
    no_sale_reason: str | None = None,
) -> dict[str, Any]:
    require_login()
    cid = require_str(client_id, "client_id")
    name = assert_trip_access(require_str(stop_id, "stop_id"))
    status = _STATUS_MAP.get(str(visit_status).strip())
    if not status:
        frappe.throw(f"Invalid visit_status: {visit_status}")

    frappe.has_permission("ZG Trip", "write", doc=name, throw=True)
    doc = frappe.get_doc("ZG Trip", name)
    doc.status = status
    # Deliberately does NOT write cid onto doc.zatgo_client_id. That field is
    # the *create* idempotency key (UNIQUE as of
    # patches.v0_2_0.make_zg_trip_client_id_unique) — overwriting it with a
    # visit's client_id would orphan the trip from its create id, so a retried
    # create would no longer find it and would insert a duplicate stop.
    # A status set is idempotent on its own; it needs no key of its own.
    if lat is not None and str(lat) != "" and frappe.db.has_column("ZG Trip", "check_in_lat"):
        doc.check_in_lat = flt(lat)
    if lng is not None and str(lng) != "" and frappe.db.has_column("ZG Trip", "check_in_lng"):
        doc.check_in_lng = flt(lng)
    if status == "Checked In" and frappe.db.has_column("ZG Trip", "check_in_at"):
        from frappe.utils import now_datetime

        doc.check_in_at = now_datetime()
    if notes is not None and frappe.db.has_column("ZG Trip", "visit_notes"):
        doc.visit_notes = notes
    if no_sale_reason is not None and frappe.db.has_column("ZG Trip", "no_sale_reason"):
        doc.no_sale_reason = no_sale_reason
    doc.save()
    frappe.db.commit()
    return ok(
        {
            "name": doc.name,
            "erp_name": doc.name,
            "client_id": cid,
            "id": doc.name,
            "status": doc.status,
            "customer": doc.customer,
            "address": doc.address,
            "sequence": doc.sequence,
            "lat": doc.lat,
            "lng": doc.lng,
            "check_in_lat": getattr(doc, "check_in_lat", None),
            "check_in_lng": getattr(doc, "check_in_lng", None),
            "sales_invoice": getattr(doc, "sales_invoice", None),
        },
        meta={"stub": False, "updated": True, "source": "ZG Trip"},
    )


# ---------------------------------------------------------------------------
# Trips (route plan stops)
# ---------------------------------------------------------------------------

_TRIP_OPTIONAL_COLUMNS = (
    "sales_user",
    "warehouse",
    "vehicle",
    "route_title",
    "sales_invoice",
    "check_in_lat",
    "check_in_lng",
    "check_in_at",
    "visit_notes",
    "no_sale_reason",
)


def assert_trip_access(name: str) -> str:
    """Row-level guard: a field user may only touch their own trips.

    `frappe.has_permission("ZG Trip", ...)` is role-level only — now that
    VanSale User holds create/write on the DocType, every write path has to
    check the assignment itself or one salesperson could edit another's route.
    """
    if not frappe.db.exists("ZG Trip", name):
        frappe.throw(f"ZG Trip {name} not found")
    if is_vansale_admin():
        return name
    owner = None
    if frappe.db.has_column("ZG Trip", "sales_user"):
        owner = frappe.db.get_value("ZG Trip", name, "sales_user")
    owner = owner or frappe.db.get_value("ZG Trip", name, "owner")
    if owner and owner != frappe.session.user:
        frappe.throw(
            "Access denied: You can only change stops on your own route.",
            frappe.PermissionError,
        )
    return name


def _trip_payload(doc: Any) -> dict[str, Any]:
    payload = {
        "id": doc.name,
        "name": doc.name,
        "erp_name": doc.name,
        "title": doc.title,
        "customer": doc.customer,
        "address": doc.address or "",
        "sequence": doc.sequence,
        "lat": doc.lat,
        "lng": doc.lng,
        "status": doc.status,
        "planned_at": str(doc.planned_at or ""),
    }
    for col in _TRIP_OPTIONAL_COLUMNS:
        payload[col] = getattr(doc, col, None)
    return payload


def _next_trip_sequence(sales_user: str | None, planned_at: Any) -> int:
    """One more than the highest sequence already planned for that day."""
    filters: dict[str, Any] = {}
    if sales_user and frappe.db.has_column("ZG Trip", "sales_user"):
        filters["sales_user"] = sales_user
    if planned_at:
        day = getdate(planned_at)
        filters["planned_at"] = ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]
    rows = frappe.get_all(
        "ZG Trip",
        filters=filters or None,
        fields=["sequence"],
        order_by="sequence desc",
        limit=1,
    )
    if not rows:
        return 1
    return int(rows[0].get("sequence") or 0) + 1


def create_trip(
    client_id: str,
    customer: str,
    planned_at: str | None = None,
    address: str | None = None,
    sequence: int | str | None = None,
    lat: float | str | None = None,
    lng: float | str | None = None,
    title: str | None = None,
    route_title: str | None = None,
    sales_user: str | None = None,
) -> dict[str, Any]:
    """Create a route-plan stop, idempotent on `client_id`.

    Mirrors create_collection's shape: pre-check by client_id, then insert
    through insert_idempotent so a concurrent duplicate resolves to the same
    document instead of a second stop.
    """
    require_login()
    cid = require_str(client_id, "client_id")
    existing = _find_by_client_id("ZG Trip", cid)
    if existing:
        doc = frappe.get_doc("ZG Trip", existing)
        return ok(
            {**_trip_payload(doc), "client_id": cid},
            meta={"stub": False, "idempotent": True, "source": "ZG Trip"},
        )

    frappe.has_permission("ZG Trip", "create", throw=True)
    party = _resolve_customer(customer)

    admin = is_vansale_admin()
    owner_user = (sales_user or "").strip() if admin else frappe.session.user
    if not admin and sales_user and sales_user != frappe.session.user:
        frappe.throw(
            "Access denied: You can only plan stops on your own route.",
            frappe.PermissionError,
        )

    profile = get_profile(owner_user or frappe.session.user)
    when = getdate(planned_at) if planned_at else getdate(nowdate())

    doc = frappe.new_doc("ZG Trip")
    doc.title = (title or "").strip() or frappe.db.get_value(
        "Customer", party, "customer_name"
    ) or party
    doc.customer = party
    doc.address = (address or "").strip() or _customer_primary_address(party)
    doc.status = "Planned"
    doc.planned_at = f"{when} 00:00:00" if not _has_time(planned_at) else planned_at
    doc.sequence = (
        int(sequence)
        if sequence not in (None, "")
        else _next_trip_sequence(owner_user, when)
    )
    if lat not in (None, ""):
        doc.lat = flt(lat)
    if lng not in (None, ""):
        doc.lng = flt(lng)

    if owner_user and frappe.db.has_column("ZG Trip", "sales_user"):
        doc.sales_user = owner_user
    if profile:
        if frappe.db.has_column("ZG Trip", "warehouse") and profile.get("warehouse"):
            doc.warehouse = profile["warehouse"]
        if frappe.db.has_column("ZG Trip", "vehicle") and profile.get("vehicle"):
            doc.vehicle = profile["vehicle"]
    if frappe.db.has_column("ZG Trip", "route_title"):
        resolved_route = (route_title or "").strip() or (
            (profile or {}).get("route_title") or ""
        )
        if resolved_route:
            doc.route_title = resolved_route
    if frappe.db.has_column("ZG Trip", "zatgo_client_id"):
        doc.zatgo_client_id = cid

    doc, created = insert_idempotent(doc, doctype="ZG Trip", client_id=cid)
    frappe.db.commit()
    return ok(
        {**_trip_payload(doc), "client_id": cid},
        meta={
            "stub": False,
            "created": created,
            "idempotent": not created,
            "source": "ZG Trip",
        },
    )


def _has_time(raw: str | None) -> bool:
    return bool(raw) and (" " in str(raw) or "T" in str(raw))


def _customer_primary_address(customer: str) -> str:
    """Best-effort address text so a stop shows something useful in the app."""
    try:
        from frappe.contacts.doctype.address.address import get_default_address

        name = get_default_address("Customer", customer)
        if not name:
            return ""
        addr = frappe.get_doc("Address", name)
        parts = [addr.address_line1, addr.address_line2, addr.city]
        return ", ".join(p for p in parts if p)
    except Exception:
        return ""


def update_trip(
    name: str,
    planned_at: str | None = None,
    address: str | None = None,
    sequence: int | str | None = None,
    lat: float | str | None = None,
    lng: float | str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    require_login()
    trip = assert_trip_access(require_str(name, "name"))
    doc = frappe.get_doc("ZG Trip", trip)
    if planned_at not in (None, ""):
        doc.planned_at = planned_at if _has_time(planned_at) else f"{getdate(planned_at)} 00:00:00"
    if address is not None:
        doc.address = address
    if sequence not in (None, ""):
        doc.sequence = int(sequence)
    if lat not in (None, ""):
        doc.lat = flt(lat)
    if lng not in (None, ""):
        doc.lng = flt(lng)
    if title not in (None, ""):
        doc.title = title
    doc.save()
    frappe.db.commit()
    return ok(
        _trip_payload(doc),
        meta={"stub": False, "updated": True, "source": "ZG Trip"},
    )


def reorder_trips(stops: Any) -> dict[str, Any]:
    """Apply new sequence numbers to a set of stops in one shot.

    `stops` is a list of {"name": <ZG Trip>, "sequence": <int>} — the output
    of the client's route optimizer. Only `sequence` is written, so this can
    never disturb a visit already in progress.
    """
    require_login()
    rows = _normalize_reorder(stops)
    if not rows:
        frappe.throw("No stops to reorder")

    updated = []
    for row in rows:
        trip = assert_trip_access(row["name"])
        frappe.db.set_value("ZG Trip", trip, "sequence", row["sequence"])
        updated.append({"name": trip, "sequence": row["sequence"]})
    frappe.db.commit()
    return ok(
        {"name": updated[0]["name"], "erp_name": updated[0]["name"], "stops": updated},
        meta={"stub": False, "updated": len(updated), "source": "ZG Trip"},
    )


def _normalize_reorder(stops: Any) -> list[dict[str, Any]]:
    import json

    raw = stops
    if isinstance(raw, str):
        raw = json.loads(raw or "[]")
    if not isinstance(raw, (list, tuple)):
        frappe.throw("stops must be a list of {name, sequence}")
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            frappe.throw("stops must be a list of {name, sequence}")
        name = require_str(entry.get("name") or entry.get("id") or "", "stops[].name")
        seq = entry.get("sequence")
        if seq in (None, ""):
            frappe.throw(f"Missing sequence for stop {name}")
        out.append({"name": name, "sequence": int(seq)})
    return out
