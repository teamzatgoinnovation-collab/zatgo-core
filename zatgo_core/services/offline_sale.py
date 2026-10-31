"""Counter sales the POS made without a connection, as the server sees them when they finally arrive.

The customer has already paid and left, so a late sale is **posted** -- at the server's own figures, on its original date and
time -- and, where reality moved on (price, tax, stock, item, discount), a review entry (ZG Offline Sale Issue) is opened for a
manager. Only a sale that cannot be posted safely is refused: an item that was disabled meanwhile (ERPNext itself refuses to
sell one), an unknown item, a closed fiscal period, a time in the future or older than the site's limit, a payment method not
allowed offline. Idempotency is untouched: the sale is still keyed on its
`zatgo_client_id` (services/idempotency.py), so a replay returns the first result.

Settings: ZG POS Settings -> Offline (services/pos_settings.py::offline_policy). Used by services/retail_pos_service.py.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import frappe
from frappe.utils import cint, flt, get_datetime, now_datetime
from frappe.utils.data import get_system_timezone

from zatgo_core.services import pos_settings

ISSUE_DOCTYPE = "ZG Offline Sale Issue"
SKEW_MINUTES = 10  # a device clock may run this far ahead of the server
GRACE_HOURS = 24  # on top of the site's offline limit: a sale made at the limit still has to reach the server
LATE_HOURS = 24  # a sale posted later than this after it was made is listed for review
TOLERANCE = 0.01

LATE = "Late sale"
PRICE = "Price changed"
TOTAL = "Total differs"
STOCK = "Negative stock"
DISCOUNT = "Discount over cap"


class PaymentPendingError(frappe.ValidationError):
    """The invoice is posted but its payment is not: the caller retries the same client_id. 503, so clients that sort errors
    by status code treat it as transient (a plain validation error is 417 and means 'park this sale')."""

    http_status_code = 503


@dataclass
class OfflineSale:
    sale_time: dt.datetime  # site timezone, naive
    offline_ref: str
    device_id: str
    expected_total: float | None
    expected_tax: float | None


def _site_time(text: str) -> dt.datetime:
    parsed = get_datetime(text)
    if parsed.tzinfo is not None:
        from zoneinfo import ZoneInfo

        parsed = parsed.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)
    return parsed


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return flt(value)


def parse(
    offline: Any,
    sale_datetime: str | None,
    offline_ref: str | None,
    device_id: str | None,
    expected_total: Any = None,
    expected_tax: Any = None,
) -> OfflineSale | None:
    """None for an ordinary (online) sale. For an offline one: the sale, after the site's policy and the clock were checked."""
    if not cint(offline):
        return None
    policy = pos_settings.offline_policy()
    if not policy["enabled"]:
        frappe.throw("Offline sales are not enabled on this site (ZG POS Settings -> Offline).")
    if not (sale_datetime or "").strip():
        frappe.throw("An offline sale needs sale_datetime: the time it was paid.")
    try:
        when = _site_time(str(sale_datetime))
    except Exception:
        frappe.throw(f"sale_datetime is not a date and time: {sale_datetime}")
    now = now_datetime()
    if when > now + dt.timedelta(minutes=SKEW_MINUTES):
        frappe.throw("The sale time is in the future: check the clock of the POS device.")
    limit = dt.timedelta(hours=policy["max_offline_hours"] + GRACE_HOURS)
    if now - when > limit:
        frappe.throw(
            f"This sale is older than the offline limit ({policy['max_offline_hours']} h): a manager has to enter it."
        )
    return OfflineSale(
        sale_time=when,
        offline_ref=(offline_ref or "").strip()[:40],
        device_id=(device_id or "").strip()[:40],
        expected_total=_opt_float(expected_total),
        expected_tax=_opt_float(expected_tax),
    )


def check_method(sale: OfflineSale, method_key: str) -> None:
    """Cash is always allowed offline; card and wallet only when the site allows them (a card cannot be checked offline)."""
    if method_key != "cash" and not pos_settings.offline_policy()["allow_card_offline"]:
        frappe.throw("Only cash can be taken offline on this site (ZG POS Settings -> Offline).")


def apply_to_invoice(si: Any, sale: OfflineSale) -> None:
    """The invoice carries the sale's own date and time, the receipt number the cashier printed, and may take stock below zero
    (services/../overrides/sales_invoice.py reads the flag; Stock Settings are never touched)."""
    si.set_posting_time = 1
    si.posting_date = sale.sale_time.date()
    si.posting_time = sale.sale_time.strftime("%H:%M:%S")
    if sale.offline_ref and frappe.get_meta("Sales Invoice").has_field("zg_offline_receipt"):
        si.zg_offline_receipt = sale.offline_ref
    si.flags.zg_offline_sale = True


def discount_percent(rows: list[dict[str, Any]], discount_type: str | None, discount_value: Any) -> float:
    kind = (discount_type or "").strip().lower()
    value = flt(discount_value)
    if kind in ("", "none") or value <= 0:
        return 0.0
    if kind == "percent":
        return value
    subtotal = sum(flt(r["qty"]) * flt(r["rate"]) for r in rows)
    return value / subtotal * 100 if subtotal > 0 else 0.0


def discount_problem(rows: list[dict[str, Any]], discount_type: str | None, discount_value: Any) -> str | None:
    """Why the discount is not allowed by ZG POS Settings (allow_discounts / max_discount_percent), or None."""
    percent = discount_percent(rows, discount_type, discount_value)
    if percent <= 0:
        return None
    allow, cap = pos_settings.discount_policy()
    if not allow:
        return "Discounts are switched off for the POS (ZG POS Settings)."
    if percent > cap + 0.005:
        return f"A discount of {percent:.2f}% is above the cap of {cap:g}% (ZG POS Settings)."
    return None


def price_differences(rows: list[dict[str, Any]]) -> list[str]:
    """Lines whose price is not the Item's list price today (offline prices come from a copy that may be days old)."""
    found = []
    for r in rows:
        list_price = flt(frappe.db.get_value("Item", r["item_code"], "standard_rate"))
        if list_price > 0 and abs(flt(r["rate"]) - list_price) > 0.005:
            found.append(f"{r['item_code']}: sold at {flt(r['rate']):g}, list price now {list_price:g}")
    return found


def refuse_disabled(rows: list[dict[str, Any]]) -> None:
    """ERPNext will not sell a disabled Item (stock/doctype/item/item.py::validate_end_of_life) and posting around that rule would
    mean editing the Item or skipping validation, so such a sale is refused with a clear reason and waits for a manager."""
    gone = [r["item_code"] for r in rows if frappe.db.get_value("Item", r["item_code"], "disabled")]
    if gone:
        frappe.throw(
            f"Item {', '.join(gone)} was disabled after this sale was made: a manager has to enter it (the receipt was already given)."
        )


def negative_stock(si: Any) -> list[str]:
    found = []
    for line in si.items:
        qty = flt(frappe.db.get_value("Bin", {"item_code": line.item_code, "warehouse": line.warehouse}, "actual_qty"))
        if qty < 0:
            found.append(f"{line.item_code} at {line.warehouse}: {qty:g} on hand")
    return found


def collect_issues(
    sale: OfflineSale,
    si: Any,
    rows: list[dict[str, Any]],
    *,
    discount_message: str | None,
    price_notes: list[str],
) -> list[tuple[str, str]]:
    """Everything about this late sale a manager should look at, as (kind, detail). Called once the invoice is posted."""
    issues: list[tuple[str, str]] = []
    delay = now_datetime() - sale.sale_time
    if delay > dt.timedelta(hours=LATE_HOURS):
        issues.append((LATE, f"Made {sale.sale_time:%Y-%m-%d %H:%M}, posted {delay.total_seconds() / 3600:.0f} h later."))
    if price_notes:
        issues.append((PRICE, "; ".join(price_notes)))
    if sale.expected_total is not None and abs(flt(si.grand_total) - sale.expected_total) > TOLERANCE:
        issues.append(
            (TOTAL, f"Receipt showed {sale.expected_total:.2f}, invoice {si.name} posted {flt(si.grand_total):.2f} (tax is the server's).")
        )
    elif sale.expected_tax is not None and abs(flt(si.total_taxes_and_charges) - sale.expected_tax) > TOLERANCE:
        issues.append((TOTAL, f"Receipt tax {sale.expected_tax:.2f}, invoice tax {flt(si.total_taxes_and_charges):.2f}."))
    negative = negative_stock(si)
    if negative:
        issues.append((STOCK, "; ".join(negative)))
    if discount_message:
        issues.append((DISCOUNT, discount_message))
    return issues


def record_issues(sale: OfflineSale, si: Any, client_id: str, issues: list[tuple[str, str]]) -> str | None:
    """One review entry per sale (unique client_id): a replay never opens a second one. Returns its name."""
    if not issues or not frappe.db.exists("DocType", ISSUE_DOCTYPE):
        return None
    existing = frappe.db.get_value(ISSUE_DOCTYPE, {"client_id": client_id}, "name")
    if existing:
        return existing
    doc = frappe.get_doc(
        {
            "doctype": ISSUE_DOCTYPE,
            "client_id": client_id,
            "sales_invoice": si.name,
            "status": "Open",
            "issue_kinds": ", ".join(kind for kind, _ in issues),
            "detail": "\n".join(f"{kind}: {text}" for kind, text in issues),
            "cashier": frappe.session.user,
            "device_id": sale.device_id,
            "offline_ref": sale.offline_ref,
            "sale_time": sale.sale_time,
            "synced_at": now_datetime(),
            "expected_total": sale.expected_total,
            "posted_total": flt(si.grand_total),
        }
    )
    try:
        doc.insert(ignore_permissions=True)
    except frappe.UniqueValidationError:
        frappe.db.rollback()
        return frappe.db.get_value(ISSUE_DOCTYPE, {"client_id": client_id}, "name")
    return doc.name


def issues_of(client_id: str) -> dict[str, Any]:
    """`meta.offline` of the response: what the review entry of this sale says (empty when there is none)."""
    if not frappe.db.exists("DocType", ISSUE_DOCTYPE):
        return {"review": False, "issues": []}
    row = frappe.db.get_value(ISSUE_DOCTYPE, {"client_id": client_id}, ["name", "detail"], as_dict=True)
    if not row:
        return {"review": False, "issues": []}
    pairs = []
    for line in (row.detail or "").split("\n"):
        kind, _, text = line.partition(": ")
        if kind:
            pairs.append({"kind": kind, "detail": text})
    return {"review": True, "issues": pairs, "issue": row.name}
