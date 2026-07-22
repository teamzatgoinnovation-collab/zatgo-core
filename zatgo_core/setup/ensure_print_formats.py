"""Ensure VanSale Tax Invoice Print Format exists (bilingual A4)."""

from __future__ import annotations

import frappe

PRINT_FORMAT_NAME = "VanSale Tax Invoice"

# Jinja HTML approximating INV-0009 bilingual tax invoice layout.
_HTML = r"""
<style>
  .vti { font-family: DejaVu Sans, Arial, sans-serif; font-size: 11px; color: #111; }
  .vti * { box-sizing: border-box; }
  .vti-title { text-align: center; font-size: 18px; font-weight: 700; margin: 0 0 4px; }
  .vti-title-ar { text-align: center; font-size: 16px; font-weight: 700; margin: 0 0 12px; direction: rtl; }
  .vti-head { width: 100%; border-collapse: collapse; margin-bottom: 14px; }
  .vti-head td { vertical-align: top; padding: 2px 4px; }
  .vti-seller { font-size: 12px; line-height: 1.45; }
  .vti-seller .name { font-weight: 700; font-size: 13px; direction: rtl; }
  .vti-meta { text-align: right; white-space: nowrap; }
  .vti-meta .ar { direction: rtl; color: #444; font-size: 10px; }
  .vti-qr { text-align: center; }
  .vti-qr img { width: 110px; height: 110px; }
  .vti-cust { width: 100%; margin: 8px 0 12px; border-collapse: collapse; }
  .vti-cust td { padding: 3px 4px; vertical-align: top; }
  .vti-cust .lbl { width: 120px; white-space: nowrap; }
  .vti-cust .ar { text-align: right; direction: rtl; color: #333; width: 140px; }
  .vti-table { width: 100%; border-collapse: collapse; margin-top: 6px; }
  .vti-table th, .vti-table td {
    border: 1px solid #222; padding: 5px 4px; text-align: center; font-size: 10px;
  }
  .vti-table th { background: #f3f3f3; font-weight: 700; }
  .vti-table .desc { text-align: left; }
  .vti-table .empty td { height: 18px; border-left: 1px solid #222; border-right: 1px solid #222; border-top: none; border-bottom: 1px solid #ddd; }
  .vti-foot { width: 100%; margin-top: 14px; border-collapse: collapse; }
  .vti-foot td { vertical-align: top; padding: 4px; }
  .vti-totals { width: 100%; border-collapse: collapse; }
  .vti-totals td { border: 1px solid #222; padding: 5px 8px; }
  .vti-totals .k { text-align: left; }
  .vti-totals .ar { text-align: right; direction: rtl; }
  .vti-totals .v { text-align: right; font-weight: 700; width: 90px; }
  .vti-sign { margin-top: 18px; }
</style>
{%- set company = frappe.get_doc("Company", doc.company) -%}
{%- set settings = None -%}
{%- if frappe.db.exists("DocType", "ZG Company Settings") -%}
  {%- set sname = frappe.db.get_value("ZG Company Settings", {"company": doc.company}, "name") -%}
  {%- if sname -%}{%- set settings = frappe.get_doc("ZG Company Settings", sname) -%}{%- endif -%}
{%- endif -%}
{%- set vat_no = (settings.tax_id if settings and settings.tax_id else company.tax_id) or "" -%}
{%- set phone = company.phone or company.mobile_no or "" -%}
{%- set cr = company.get("company_registration") or company.get("registration_details") or "" -%}
{%- set cust = frappe.get_doc("Customer", doc.customer) -%}
{%- set cust_tax = cust.tax_id or "" -%}
{%- set cust_phone = cust.mobile_no or cust.get("phone") or "" -%}
{%- set cust_addr = doc.address_display or "—" -%}
{%- set qr_uri = frappe.get_attr("zatgo_core.services.zatca_qr.tlv_to_png_data_uri")(doc.get("zatca_qr_base64")) if doc.get("zatca_qr_base64") else "" -%}
{%- set salesman = frappe.db.get_value("User", doc.owner, "full_name") or doc.owner -%}
{%- set paid_by = doc.get("mode_of_payment") or "" -%}
{%- if not paid_by -%}
  {%- set pe = frappe.db.get_value("Payment Entry Reference", {"reference_doctype": "Sales Invoice", "reference_name": doc.name}, "parent") -%}
  {%- if pe -%}{%- set paid_by = frappe.db.get_value("Payment Entry", pe, "mode_of_payment") or "Cash" -%}{%- endif -%}
{%- endif -%}
{%- set prev_bal = 0 -%}
{%- set closing = frappe.utils.flt(doc.outstanding_amount or 0) -%}
{%- set words = frappe.utils.money_in_words(doc.grand_total or 0, doc.currency or company.default_currency) -%}
{%- set n_items = (doc.items or [])|length -%}
{%- set pad = 8 - n_items if n_items < 8 else 0 -%}

<div class="vti">
  <div class="vti-title">TAX INVOICE</div>
  <div class="vti-title-ar">فاتورة ضريبية</div>

  <table class="vti-head">
    <tr>
      <td style="width:34%">
        <div class="vti-seller">
          <div class="name">{{ company.company_name }}</div>
          <div>VAT No:{{ vat_no }}</div>
          <div>Cr:{{ cr or "—" }}</div>
          <div>Mob:{{ phone or "—" }}</div>
        </div>
      </td>
      <td style="width:32%" class="vti-qr">
        {% if qr_uri %}<img src="{{ qr_uri }}" alt="QR"/>{% endif %}
      </td>
      <td style="width:34%" class="vti-meta">
        <div><b>Invoice No:</b> {{ doc.name }}</div>
        <div class="ar">رقم الفاتورة</div>
        <div style="margin-top:8px"><b>Date:</b> {{ frappe.utils.formatdate(doc.posting_date, "dd-MM-yyyy") }}</div>
        <div class="ar">تاريخ</div>
        <div style="margin-top:8px"><b>Supply Date:</b> {{ frappe.utils.formatdate(doc.posting_date, "dd-MM-yyyy") }}</div>
        <div class="ar">تاريخ التوريد</div>
      </td>
    </tr>
  </table>

  <table class="vti-cust">
    <tr>
      <td class="lbl">Customer Name :</td>
      <td>{{ doc.customer_name or doc.customer }}</td>
      <td class="ar">: اسم الزبون</td>
    </tr>
    <tr>
      <td class="lbl">TAX No :</td>
      <td>{{ cust_tax or "—" }}</td>
      <td class="ar">: رقم ضريبة القيمة المضافة</td>
    </tr>
    <tr>
      <td class="lbl">Address :</td>
      <td>{{ cust_addr | striptags or "—" }}</td>
      <td class="ar">: عنوان</td>
    </tr>
    <tr>
      <td class="lbl">Phone :</td>
      <td>{{ cust_phone or "—" }}</td>
      <td class="ar">: هاتف</td>
    </tr>
  </table>

  <table class="vti-table">
    <thead>
      <tr>
        <th>Sl<br/><span style="font-weight:400">رقم</span></th>
        <th>Description<br/><span style="font-weight:400">وصف</span></th>
        <th>Unit<br/><span style="font-weight:400">وحدة</span></th>
        <th>Qty<br/><span style="font-weight:400">الكمية</span></th>
        <th>Unit Price<br/><span style="font-weight:400">السعر</span></th>
        <th>Gross<br/><span style="font-weight:400">إجمالي</span></th>
        <th>VAT %<br/><span style="font-weight:400">ضريبة %</span></th>
        <th>VAT<br/><span style="font-weight:400">ضريبة</span></th>
        <th>Total<br/><span style="font-weight:400">مجموع</span></th>
      </tr>
    </thead>
    <tbody>
      {% for item in doc.items %}
      {%- set qty = frappe.utils.flt(item.qty) -%}
      {%- set rate = frappe.utils.flt(item.rate) -%}
      {%- set net = frappe.utils.flt(item.net_amount or item.amount) -%}
      {%- set tax_amt = frappe.utils.flt(item.get("tax_amount") or 0) -%}
      {%- if not tax_amt and doc.total and doc.total_taxes_and_charges and n_items -%}
        {%- set tax_amt = frappe.utils.flt(doc.total_taxes_and_charges) * (net / frappe.utils.flt(doc.total)) -%}
      {%- endif -%}
      {%- set line_total = frappe.utils.flt(item.amount or (net + tax_amt)) -%}
      {%- set vat_pct = 0 -%}
      {%- if net -%}{%- set vat_pct = (tax_amt / net) * 100 -%}{%- endif -%}
      <tr>
        <td>{{ loop.index }}</td>
        <td class="desc">{{ item.item_name or item.item_code }}</td>
        <td>{{ item.uom or "Nos" }}</td>
        <td>{{ "%.2f"|format(qty) }}</td>
        <td>{{ "%.2f"|format(rate) }}</td>
        <td>{{ "%.2f"|format(net) }}</td>
        <td>{{ "%.2f"|format(vat_pct) }}</td>
        <td>{{ "%.2f"|format(tax_amt) }}</td>
        <td>{{ "%.2f"|format(line_total) }}</td>
      </tr>
      {% endfor %}
      {% for i in range(pad) %}
      <tr class="empty"><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
      {% endfor %}
    </tbody>
  </table>

  <table class="vti-foot">
    <tr>
      <td style="width:55%">
        <div><b>Amount in Words :</b> المبلغ بالكلمات</div>
        <div style="margin:6px 0 10px">{{ words }}</div>
        <div><b>Paid by:</b> {{ paid_by or "—" }}</div>
        <div style="margin-top:10px">Previous Balance: الرصيد السابق &nbsp; {{ "%.2f"|format(frappe.utils.flt(prev_bal)) }}</div>
        <div>Closing Balance: الرصيد الحالي &nbsp; {{ "%.2f"|format(closing) }}</div>
        <div class="vti-sign">Received By : / المستلم :</div>
      </td>
      <td style="width:45%">
        <table class="vti-totals">
          <tr>
            <td class="k">Total Gross</td>
            <td class="ar">مجموع إجمالي</td>
            <td class="v">{{ "%.2f"|format(frappe.utils.flt(doc.net_total or doc.total)) }}</td>
          </tr>
          <tr>
            <td class="k">Discount</td>
            <td class="ar">خصم</td>
            <td class="v">{{ "%.2f"|format(frappe.utils.flt(doc.discount_amount)) }}</td>
          </tr>
          <tr>
            <td class="k">Total VAT</td>
            <td class="ar">مجموع الضريبة</td>
            <td class="v">{{ "%.2f"|format(frappe.utils.flt(doc.total_taxes_and_charges)) }}</td>
          </tr>
          <tr>
            <td class="k"><b>Grand Total</b></td>
            <td class="ar"><b>صافي إجمالي</b></td>
            <td class="v">{{ "%.2f"|format(frappe.utils.flt(doc.grand_total)) }}</td>
          </tr>
        </table>
        <div style="margin-top:14px; text-align:right">
          <div><b>SalesMan:</b> {{ salesman }}</div>
          <div>Mobile No: {{ phone or "—" }}</div>
        </div>
      </td>
    </tr>
  </table>
</div>
"""


def ensure_print_formats() -> None:
    """Create or update the VanSale Tax Invoice print format."""
    if frappe.db.exists("Print Format", PRINT_FORMAT_NAME):
        doc = frappe.get_doc("Print Format", PRINT_FORMAT_NAME)
        doc.html = _HTML
        doc.custom_format = 1
        doc.raw_printing = 0
        doc.disabled = 0
        doc.print_format_type = "Jinja"
        doc.doc_type = "Sales Invoice"
        doc.standard = "No"
        doc.module = "ZatGo Core"
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc(
            {
                "doctype": "Print Format",
                "name": PRINT_FORMAT_NAME,
                "doc_type": "Sales Invoice",
                "module": "ZatGo Core",
                "standard": "No",
                "custom_format": 1,
                "print_format_type": "Jinja",
                "html": _HTML,
                "disabled": 0,
            }
        ).insert(ignore_permissions=True)
    frappe.db.commit()
