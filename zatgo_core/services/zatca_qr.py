"""ZATCA Phase 2 simplified tax invoice QR (TLV → Base64)."""

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


def generate_and_store_zatca_qr(doc: Any) -> str:
    """Build simplified ZATCA QR for a Sales Invoice and persist custom field."""
    company = doc.company
    seller_name = frappe.db.get_value("Company", company, "company_name") or company
    vat_number = _seller_vat(company)
    qr = build_zatca_tlv_base64(
        seller_name=str(seller_name),
        vat_number=vat_number or "000000000000000",
        timestamp=_invoice_timestamp(doc),
        invoice_total=doc.grand_total or 0,
        vat_amount=getattr(doc, "total_taxes_and_charges", None) or 0,
    )
    if frappe.get_meta("Sales Invoice").has_field("zatca_qr_base64"):
        frappe.db.set_value("Sales Invoice", doc.name, "zatca_qr_base64", qr, update_modified=False)
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
