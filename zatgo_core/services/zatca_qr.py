"""ZATCA Phase 1 simplified tax invoice QR (TLV → Base64).

No cryptographic stamp, no CSID, no XML invoice, no clearance/reporting API —
see .claude/rules/accounting.md for the Phase 1/Phase 2 distinction.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

import frappe
from frappe.utils import flt, get_datetime


def _tlv(tag: int, value: str) -> bytes:
    encoded = (value or "").encode("utf-8")
    return bytes([tag, len(encoded)]) + encoded


def build_zatca_tlv_base64(
    *,
    seller_name: str,
    vat_number: str,
    timestamp: str,
    invoice_total: float | str,
    vat_amount: float | str,
) -> str:
    payload = b"".join(
        [
            _tlv(1, seller_name),
            _tlv(2, vat_number),
            _tlv(3, timestamp),
            _tlv(4, f"{flt(invoice_total):.2f}"),
            _tlv(5, f"{flt(vat_amount):.2f}"),
        ]
    )
    return base64.b64encode(payload).decode("ascii")


def _seller_vat(company: str) -> str:
    if frappe.db.exists("DocType", "ZG Company Settings"):
        row = frappe.db.get_value(
            "ZG Company Settings",
            {"company": company},
            ["tax_id"],
            as_dict=True,
        )
        if row and row.get("tax_id"):
            return str(row.tax_id).strip()
    tax_id = frappe.db.get_value("Company", company, "tax_id")
    return str(tax_id or "").strip()


def _invoice_timestamp(doc: Any) -> str:
    posting_date = getattr(doc, "posting_date", None)
    posting_time = getattr(doc, "posting_time", None)
    if posting_date and posting_time:
        try:
            dt = get_datetime(f"{posting_date} {posting_time}")
            return dt.isoformat()
        except Exception:
            pass
    if posting_date:
        return f"{posting_date}T00:00:00"
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def zatca_qr_data_uri(doc: Any) -> str:
    """One-shot: build this invoice's ZATCA Phase 1 QR and render it as a
    self-contained PNG data URI, computed fresh from the invoice's own
    fields at print time.

    For print formats that would otherwise display a QR from an "Attach
    Image"-type field (e.g. a third-party app's generated PNG file) --
    that file can be deleted from the invoice's attachments (by a user
    cleaning up attachments, or anything else touching the File doctype),
    silently breaking the QR on every future print. The five values ZATCA
    Phase 1's TLV format encodes (seller name, VAT number, timestamp,
    invoice total, VAT total) are all plain fields already on the
    invoice/company, so there's no need to depend on a stored image at
    all -- read-only, no DB write, safe to call directly from a print
    format's Jinja.
    """
    if not getattr(doc, "company", None):
        return ""
    company = doc.company
    seller_name = frappe.db.get_value("Company", company, "company_name") or company
    vat_number = _seller_vat(company)
    grand_total = doc.get("grand_total") or 0
    taxes = doc.get("total_taxes_and_charges") or 0
    if bool(int(doc.get("is_return") or 0)):
        grand_total = abs(flt(grand_total))
        taxes = abs(flt(taxes))
    tlv_b64 = build_zatca_tlv_base64(
        seller_name=str(seller_name),
        vat_number=vat_number or "000000000000000",
        timestamp=_invoice_timestamp(doc),
        invoice_total=grand_total,
        vat_amount=taxes,
    )
    return tlv_to_png_data_uri(tlv_b64)


def tlv_to_png_data_uri(tlv_b64: str | None) -> str:
    """Encode ZATCA TLV base64 string as a PNG QR data URI for print formats."""
    if not tlv_b64:
        return ""
    try:
        import qrcode
        from io import BytesIO

        img = qrcode.make(str(tlv_b64))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        frappe.log_error(title="ZATCA QR PNG render failed", message=frappe.get_traceback())
        return ""


def generate_and_store_zatca_qr(doc: Any) -> str:
    """Build simplified ZATCA QR for a Sales Invoice and persist custom field."""
    company = doc.company
    seller_name = frappe.db.get_value("Company", company, "company_name") or company
    vat_number = _seller_vat(company)
    # Return (credit-note) invoices carry negative totals in ERPNext; the simplified
    # phase-1 TLV here has no invoice-subtype tag to convey "return", so emit the
    # magnitude only. Full ZATCA credit-note encoding is out of scope for now.
    is_return = bool(int(getattr(doc, "is_return", 0) or 0))
    grand_total = doc.grand_total or 0
    taxes = getattr(doc, "total_taxes_and_charges", None) or 0
    if is_return:
        grand_total = abs(flt(grand_total))
        taxes = abs(flt(taxes))
    qr = build_zatca_tlv_base64(
        seller_name=str(seller_name),
        vat_number=vat_number or "000000000000000",
        timestamp=_invoice_timestamp(doc),
        invoice_total=grand_total,
        vat_amount=taxes,
    )
    if frappe.get_meta("Sales Invoice").has_field("zatca_qr_base64"):
        values = {"zatca_qr_base64": qr}
        # For print_designer's image binding (§ events/print_fields.py) -- same
        # timing gap as the field it mirrors: this is a direct db.set_value, so
        # the validate-hooked populate_print_fields never sees a fresh QR unless
        # it's captured here too.
        if frappe.get_meta("Sales Invoice").has_field("vansale_qr_image"):
            values["vansale_qr_image"] = tlv_to_png_data_uri(qr)
        frappe.db.set_value("Sales Invoice", doc.name, values, update_modified=False)
        doc.zatca_qr_base64 = qr
    return qr


def zatca_fields_from_doc(doc: Any) -> dict[str, Any]:
    company = doc.company
    seller_name = frappe.db.get_value("Company", company, "company_name") or company
    return {
        "seller_name": seller_name,
        "vat_number": _seller_vat(company),
        "timestamp": _invoice_timestamp(doc),
        "invoice_total": flt(doc.grand_total or 0),
        "vat_amount": flt(getattr(doc, "total_taxes_and_charges", None) or 0),
        "qr_base64": getattr(doc, "zatca_qr_base64", None)
        or (frappe.db.get_value("Sales Invoice", doc.name, "zatca_qr_base64") if doc.name else None),
    }
