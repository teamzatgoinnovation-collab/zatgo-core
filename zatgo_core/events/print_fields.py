"""Populate presentation-only computed fields the print_designer Sales
Invoice format binds to directly (its JS runtime reads real stored
fields, not arbitrary Jinja -- see patches/v0_2_1/add_print_computed_fields.py).

Every computation here already existed as inline Jinja in
setup/ensure_print_formats.py's "VanSale Tax Invoice" template -- this
only relocates it to run once per validate, not new tax/accounting logic.
"""

from __future__ import annotations

import frappe

from zatgo_core.services.zatca_qr import tlv_to_png_data_uri


def populate_print_fields(doc, method=None) -> None:
    net_total = frappe.utils.flt(doc.net_total or doc.total)
    total_tax = frappe.utils.flt(doc.total_taxes_and_charges)

    for item in doc.items:
        line_net = frappe.utils.flt(item.net_amount or item.amount)
        line_tax = frappe.utils.flt(item.get("tax_amount") or 0)
        if not line_tax and net_total and total_tax:
            line_tax = total_tax * (line_net / net_total)
        item.vansale_line_vat_rate = (line_tax / line_net * 100) if line_net else 0
        item.vansale_line_vat_amount = line_tax
        item.vansale_line_total_incl_vat = line_net + line_tax

    company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    doc.vansale_amount_in_words_print = frappe.utils.money_in_words(
        doc.grand_total or 0, doc.currency or company_currency
    )

    # Confirmed empirically (two real submits, checked against actual GL
    # Entry rows): this invoice's own GL Entries are never yet queryable
    # at hook time, whether called from validate or on_submit -- ERPNext's
    # GL posting for Sales Invoice happens after doc_events dispatch
    # completes. So this always reads state that correctly excludes the
    # current invoice, for both draft and submitted -- no docstatus branch
    # needed; just add this invoice's own total back in for "new".
    closing_now = _customer_balance(doc.customer, doc.company, doc.posting_date)
    doc.vansale_previous_balance = closing_now
    doc.vansale_new_balance = closing_now + frappe.utils.flt(doc.grand_total)

    if doc.docstatus == 0:
        doc.vansale_watermark_text = "DRAFT"
    elif doc.docstatus == 2:
        doc.vansale_watermark_text = "CANCELLED"
    elif frappe.utils.flt(doc.outstanding_amount) == 0:
        doc.vansale_watermark_text = "PAID"
    else:
        doc.vansale_watermark_text = ""

    if doc.get("zatca_qr_base64"):
        doc.vansale_qr_image = tlv_to_png_data_uri(doc.zatca_qr_base64)


def _customer_balance(customer, company, as_of_date) -> float:
    row = frappe.db.sql(
        """
        select sum(debit) - sum(credit) as bal
        from `tabGL Entry`
        where party_type='Customer' and party=%s and company=%s
          and posting_date <= %s and is_cancelled=0
        """,
        (customer, company, as_of_date),
        as_dict=True,
    )
    return frappe.utils.flt(row[0].bal) if row and row[0].bal is not None else 0
