"""Retail (Supermarket) POS: one-shot sale, payments list and dashboard counts.

The Supermarket industry reuses the restaurant POS back-office for catalog,
stock and customers (`resto_pos_admin_service`) but never touches the
restaurant-owned DocTypes (ZG Order / ZG Table / ZG KDS Ticket, hidden while
Restaurant is off). A sale is ONE submitted Sales Invoice (update_stock=1,
server-owned tax via `vansalex_service._apply_sales_taxes`, cashier discount
posted on the invoice) plus a Payment Entry for the chosen method -- both
keyed on `zatgo_client_id` through `insert_idempotent`, so a retried request
returns the existing result instead of posting a second invoice.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import frappe
from frappe.utils import flt, get_datetime, today

from zatgo_core.api.response import ok, paginated
from zatgo_core.api.validators import parse_pagination, require_login, require_str
from zatgo_core.services import offline_sale
from zatgo_core.services.offline_sale import PaymentPendingError
from zatgo_core.services.resto_pos_admin_service import _MODE_TO_KEY, _company, _stock_rows
from zatgo_core.services.resto_pos_service import (
    _MODE_OF_PAYMENT_MAP,
    _apply_discount,
    _parse_order_items,
    _reason,
    _resolve_pos_customer,
    _resolve_pos_warehouse,
)

_SOURCE = "Sales Invoice"
_MARKER = "Retail POS sale"  # Sales Invoice.remarks: how retail POS invoices are told apart
# Roles that may sell below the Item's list price (price override).
_PRICE_OVERRIDE_ROLES = {"System Manager", "Accounts Manager", "Sales Manager", "Stock Manager"}


# --- mapping ---------------------------------------------------------------


def _posted_at(si: Any) -> str:
    try:
        return str(get_datetime(f"{si.posting_date} {si.posting_time}"))
    except Exception:
        return str(si.creation or si.posting_date or "")


def _map_invoice(si: Any) -> dict[str, Any]:
    return {
        "id": si.name,
        "customer": si.customer_name or si.customer,
        "subtotal": flt(si.total),
        "discount": flt(si.discount_amount),
        "tax": flt(si.total_taxes_and_charges),
        "total": flt(si.grand_total),
        "postedAt": _posted_at(si),
    }


def _method_key(mode_of_payment: str | None) -> str:
    return _MODE_TO_KEY.get((mode_of_payment or "").lower(), "cash")


def _map_payment(pe: Any, si: Any) -> dict[str, Any]:
    return {
        "id": pe.name,
        "method": _method_key(pe.mode_of_payment),
        "amount": flt(pe.paid_amount) or flt(si.grand_total),
        "paidAt": str(pe.posting_date or ""),
    }


def _result(si: Any, pe: Any) -> dict[str, Any]:
    return {"invoice": _map_invoice(si), "payment": _map_payment(pe, si)}


def _zero_payment(si: Any, method_key: str) -> dict[str, Any]:
    """A fully discounted (zero total) sale has nothing to collect: no Payment Entry."""
    return {"id": si.name, "method": method_key, "amount": 0.0, "paidAt": str(si.posting_date or "")}


def _validate_rates(rows: list[dict[str, Any]], *, enforce_floor: bool = True) -> None:
    """Server-side price check: never negative; below the Item's list price (or free)
    only for a price-override role. Cashier discounts go through `discount_*`.
    A sale made offline (`enforce_floor=False`) was priced from a copy of the catalog that may be days old and the customer
    has paid: a differing price is posted and listed for review instead (services/offline_sale.py)."""
    can_override = bool(_PRICE_OVERRIDE_ROLES & set(frappe.get_roles()))
    for r in rows:
        rate = flt(r["rate"])
        if rate < 0:
            frappe.throw(f"Invalid price for {r['item_code']}: it cannot be negative.")
        if can_override or not enforce_floor:
            continue
        list_price = flt(frappe.db.get_value("Item", r["item_code"], "standard_rate"))
        if rate <= 0 and list_price > 0:
            frappe.throw(f"Invalid price for {r['item_code']}: a free line needs a price-override role.")
        if list_price > 0 and rate < list_price - 0.005:
            frappe.throw(
                f"Price for {r['item_code']} is below its list price ({list_price}); "
                "use a discount or ask a manager."
            )


def _resolve_customer(customer_id, customer_name, customer_phone) -> str:
    """`_resolve_pos_customer`, tolerant of two first sales creating the same customer at once."""
    try:
        return _resolve_pos_customer(customer_id, customer_name, customer_phone)
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        frappe.db.rollback()
        return _resolve_pos_customer(customer_id, customer_name, customer_phone)


def _is_naming_race(exc: Exception) -> bool:
    return bool(getattr(exc, "args", None)) and exc.args[0] == 1020


def _check_replay(si: Any, rows: list[dict[str, Any]], company: str) -> None:
    """A repeated client_id must be the same sale of the same caller, not someone else's invoice."""
    if si.company != company or (si.remarks or "") != _MARKER:
        frappe.throw("This client_id belongs to a different document; use a new one.")
    if si.owner != frappe.session.user and "System Manager" not in frappe.get_roles():
        frappe.throw("This client_id was used by another user; use a new one.", frappe.PermissionError)
    sent = sorted((r["item_code"], flt(r["qty"]), round(flt(r["rate"]), 4)) for r in rows)
    posted = sorted((i.item_code, flt(i.qty), round(flt(i.rate), 4)) for i in si.items)
    if sent != posted:
        frappe.throw("This client_id was already used for a different basket; use a new one.")


# --- sale ------------------------------------------------------------------


def _build_invoice(rows, comp, cid, customer_id, customer_name, customer_phone, discount_type, discount_value):
    from zatgo_core.services.vansalex_service import _apply_sales_taxes

    customer = _resolve_customer(customer_id, customer_name, customer_phone)
    warehouse = _resolve_pos_warehouse(comp)
    si = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": customer,
            "company": comp,
            "posting_date": today(),
            "currency": frappe.get_cached_value("Company", comp, "default_currency"),
            "update_stock": 1,
            "set_warehouse": warehouse,
            "remarks": _MARKER,
            "items": [
                {
                    "item_code": r["item_code"],
                    "item_name": r["item_name"],
                    "qty": r["qty"],
                    "rate": r["rate"],
                    "warehouse": warehouse,
                }
                for r in rows
            ],
            "zatgo_client_id": cid,
        }
    )
    _apply_discount(
        si,
        SimpleNamespace(items=[SimpleNamespace(qty=r["qty"], rate=r["rate"]) for r in rows]),
        discount_type,
        discount_value,
    )
    _apply_sales_taxes(si, comp)
    return si


def create_sale(
    items: Any,
    method: str,
    client_id: str,
    customer_id: str | None = None,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    discount_type: str | None = None,
    discount_value: float | str | None = None,
    company: str | None = None,
    offline: Any = None,
    sale_datetime: str | None = None,
    offline_ref: str | None = None,
    device_id: str | None = None,
    expected_total: Any = None,
    expected_tax: Any = None,
) -> dict[str, Any]:
    """Post a counter sale: Sales Invoice (stock out) + Payment Entry. Idempotent on `client_id`.

    `offline=1` (with `sale_datetime`, `offline_ref`, `device_id`, `expected_*`): a sale the POS made without a connection
    and sends late. It keeps its own date and time, is posted even where stock, price, tax or the discount cap no longer fit,
    and those cases open a review entry (services/offline_sale.py); `meta.offline` lists them."""
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent, submit_or_rollback
    require_login()
    cid = require_str(client_id, "client_id")
    method_key = str(method or "").lower()
    mop = _MODE_OF_PAYMENT_MAP.get(method_key)
    if not mop:
        frappe.throw(f"Unknown payment method: {method}")

    rows = _parse_order_items(items)
    if not rows:
        frappe.throw("Cannot check out an empty sale")

    frappe.has_permission("Sales Invoice", "create", throw=True)
    frappe.has_permission("Payment Entry", "create", throw=True)
    sale = offline_sale.parse(offline, sale_datetime, offline_ref, device_id, expected_total, expected_tax)
    if sale:
        offline_sale.check_method(sale, method_key)
    _validate_rates(rows, enforce_floor=sale is None)
    discount_message = offline_sale.discount_problem(rows, discount_type, discount_value)
    if discount_message and sale is None:
        frappe.throw(discount_message)

    comp = _company(company)
    si_created = False
    si = None
    existing = find_by_client_id("Sales Invoice", cid)
    if existing:
        si = frappe.get_doc("Sales Invoice", existing)
        _check_replay(si, rows, comp)
    else:
        if sale:
            offline_sale.refuse_disabled(rows)
        for attempt in range(3):
            try:
                si = _build_invoice(
                    rows, comp, cid, customer_id, customer_name, customer_phone, discount_type, discount_value
                )
                if sale:
                    offline_sale.apply_to_invoice(si, sale)
                si, si_created = insert_idempotent(si, doctype="Sales Invoice", client_id=cid)
                break
            except Exception as exc:
                # MariaDB 11.8 concurrent same-series naming race: retry, never a duplicate.
                if attempt < 2 and _is_naming_race(exc):
                    frappe.db.rollback()
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise
        if not si_created:
            _check_replay(si, rows, comp)

    posted_now = int(si.docstatus or 0) == 0
    if posted_now:
        if sale:
            si.flags.zg_offline_sale = True  # may take stock below zero (overrides/sales_invoice.py)
        # The insert above is not committed either: the rollback removes the draft too.
        submit_or_rollback(
            si,
            log_title="Retail POS Sales Invoice submit failed",
            failure=lambda exc: f"Could not post the sale: {_reason(exc)} Nothing was recorded -- fix this and retry.",
        )
    elif int(si.docstatus or 0) == 2:
        frappe.throw(f"Sales Invoice {si.name} for this sale was cancelled.")
    if sale and posted_now:
        # The invoice is committed: its review entry is too, before the payment step can fail.
        issues = offline_sale.collect_issues(
            sale,
            si,
            rows,
            discount_message=discount_message,
            price_notes=offline_sale.price_differences(rows),
        )
        offline_sale.record_issues(sale, si, cid, issues)
        frappe.db.commit()
    meta_extra = {"offline": offline_sale.issues_of(cid)} if sale else {}

    if flt(si.outstanding_amount) <= 0 and not find_by_client_id("Payment Entry", f"{cid}:pay"):
        # Fully discounted (zero total): nothing to collect, so no Payment Entry.
        return ok(
            {"invoice": _map_invoice(si), "payment": _zero_payment(si, method_key)},
            meta={"stub": False, "created": si_created, "idempotent": not si_created, "source": _SOURCE, **meta_extra},
        )

    pay_cid = f"{cid}:pay"
    existing_pe = find_by_client_id("Payment Entry", pay_cid)
    if existing_pe:
        pe = frappe.get_doc("Payment Entry", existing_pe)
    else:
        pe = get_payment_entry("Sales Invoice", si.name)
        if sale:
            pe.posting_date = si.posting_date  # the money was taken on the day of the sale
        pe.mode_of_payment = mop
        _set_paid_to(pe, mop, comp)
        _set_bank_reference(pe, si)
        pe.zatgo_client_id = pay_cid
        pe, _pe_created = insert_idempotent(pe, doctype="Payment Entry", client_id=pay_cid)
    if int(pe.docstatus or 0) == 0:
        try:
            pe.submit()
            frappe.db.commit()
        except Exception as exc:
            # Rolls back the uncommitted payment insert; the invoice was committed above (posted, unpaid).
            frappe.db.rollback()
            frappe.log_error(title="Retail POS Payment Entry submit failed", message=frappe.get_traceback())
            frappe.throw(
                f"The invoice {si.name} posted, but recording the payment failed: {_reason(exc)} Retry the payment.",
                PaymentPendingError,
            )
    frappe.db.commit()
    return ok(
        _result(si, pe),
        meta={"stub": False, "created": si_created, "idempotent": not si_created, "source": _SOURCE, **meta_extra},
    )


def _set_paid_to(pe: Any, mop: str, company: str) -> None:
    """Debit the Mode of Payment's own account (card/wallet/bank), not the company's default cash."""
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_bank_cash_account

    # Payment Entry's helper takes the document ((doc, bank_account)), like services/erpnext_writes.py passes it;
    # it returns {} when the mode has no account.
    acct = get_bank_cash_account(frappe._dict(company=company, mode_of_payment=mop), None) or {}
    account = acct.get("account")
    if not account:
        return
    currency = acct.get("account_currency")
    company_currency = frappe.get_cached_value("Company", company, "default_currency")
    if currency and currency != company_currency:
        return  # foreign-currency account: keep ERPNext's own exchange-rate handling
    pe.paid_to = account
    pe.paid_to_account_currency = currency or company_currency


def _set_bank_reference(pe: Any, si: Any) -> None:
    """ERPNext demands a reference number and date on a Payment Entry that lands in a Bank account (card, wallet and
    bank modes). A counter sale has no bank slip, so the invoice number and date stand in."""
    if pe.paid_to and frappe.get_cached_value("Account", pe.paid_to, "account_type") == "Bank":
        pe.reference_no = pe.reference_no or si.name
        pe.reference_date = pe.reference_date or si.posting_date


# --- payments --------------------------------------------------------------


def _retail_invoices(company: str, date: str, *, returns: bool = False) -> list[Any]:
    """Submitted Retail POS invoices (permission-aware) of one posting day. With
    `returns`, the credit notes of that day that reverse a retail POS invoice."""
    filters: dict[str, Any] = {
        "docstatus": 1,
        "is_return": 1 if returns else 0,
        "company": company,
        "posting_date": date,
    }
    if not returns:
        filters["remarks"] = _MARKER
    rows = frappe.get_list(
        "Sales Invoice",
        filters=filters,
        fields=["name", "grand_total", "posting_date", "total_qty", "return_against"],
        order_by="creation desc",
        limit_page_length=0,
    )
    if returns and rows:
        retail = set(
            frappe.get_all(
                "Sales Invoice",
                filters={"name": ["in", [r.return_against for r in rows if r.return_against] or [""]], "remarks": _MARKER},
                pluck="name",
            )
        )
        rows = [r for r in rows if r.return_against in retail]
    return rows


def _retail_payment_rows(company: str, date: str) -> list[dict[str, Any]]:
    """Receive Payment Entries of one posting day against retail POS invoices (permission-aware)."""
    pes = frappe.get_list(
        "Payment Entry",
        filters={
            "docstatus": 1,
            "payment_type": "Receive",
            "party_type": "Customer",
            "company": company,
            "posting_date": date,
        },
        fields=["name", "mode_of_payment", "posting_date", "paid_amount"],
        order_by="creation desc",
        limit_page_length=0,
    )
    if not pes:
        return []
    refs = frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": ["in", [p.name for p in pes]], "reference_doctype": "Sales Invoice"},
        fields=["parent", "reference_name"],
    )
    ref_of = {r.parent: r.reference_name for r in refs}
    retail = set(
        frappe.get_all(
            "Sales Invoice",
            filters={"name": ["in", list(set(ref_of.values())) or [""]], "remarks": _MARKER},
            pluck="name",
        )
    )
    out = []
    for pe in pes:
        ref = ref_of.get(pe.name)
        if ref in retail:
            out.append(
                {
                    "id": pe.name,
                    "orderId": ref,
                    "orderNumber": ref,
                    "method": _method_key(pe.mode_of_payment),
                    "amount": flt(pe.paid_amount),
                    "paidAt": str(pe.posting_date or ""),
                    "channel": "counter",
                }
            )
    return out


def list_payments(
    date: str | None = None, page: int | str = 1, page_size: int | str = 100, company: str | None = None
) -> dict[str, Any]:
    """Payment Entries received against retail POS invoices for ONE posting day
    (`date` YYYY-MM-DD, default today), newest first. Same row shape as
    resto_pos.payments.list (`orderId` / `orderNumber` carry the invoice id)."""
    require_login()
    frappe.has_permission("Payment Entry", "read", throw=True)
    page_i, size_i, start = parse_pagination(page, page_size)
    comp = _company(company)
    out = _retail_payment_rows(comp, date or today())
    return paginated(
        out[start : start + size_i],
        page=page_i,
        page_size=size_i,
        total=len(out),
        sort="creation desc",
    )


# --- dashboard -------------------------------------------------------------


def dashboard_counts(company: str | None = None) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Sales Invoice", "read", throw=True)
    comp = _company(company)
    day = today()
    invoices = _retail_invoices(comp, day)
    returns = _retail_invoices(comp, day, returns=True)
    # Credit notes carry negative totals/qty: adding them nets the day.
    revenue = sum(flt(i.grand_total) for i in invoices) + sum(flt(r.grand_total) for r in returns)
    sold = sum(flt(i.total_qty) for i in invoices) + sum(flt(r.total_qty) for r in returns)
    payments_today = len(_retail_payment_rows(comp, day))

    low = 0
    try:
        low = sum(1 for r in _stock_rows(comp, None) if r["reorderAt"] and r["onHand"] <= r["reorderAt"])
    except Exception:
        # No warehouse configured yet: nothing to report, not an error for the dashboard.
        frappe.clear_last_message()
    return ok(
        {
            "todaySales": revenue,
            "paymentsToday": payments_today,
            "revenueToday": revenue,
            "lowStock": low,
            "itemsSoldToday": sold,
        },
        meta={"stub": False, "source": _SOURCE},
    )
