"""Ensure VanSale Tax Invoice Print Format exists (bilingual A4)."""

from __future__ import annotations

import re

import frappe

from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

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
{%- set phone = company.phone_no or "" -%}
{%- set cr = company.get("company_registration") or company.get("registration_details") or "" -%}
{%- set cust = frappe.get_doc("Customer", doc.customer) -%}
{%- set cust_tax = cust.tax_id or "" -%}
{%- set cust_phone = cust.mobile_no or cust.get("phone") or "" -%}
{%- set cust_addr = doc.address_display or "—" -%}
{%- set qr_uri = tlv_to_png_data_uri(doc.get("zatca_qr_base64")) if doc.get("zatca_qr_base64") else "" -%}
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
  {#- A return is a credit note, not a second tax invoice. -#}
  <div class="vti-title">{{ "CREDIT NOTE" if doc.get("is_return") else "TAX INVOICE" }}</div>
  <div class="vti-title-ar">{{ "إشعار دائن" if doc.get("is_return") else "فاتورة ضريبية" }}</div>
  {% if doc.get("is_return") and doc.get("return_against") %}<div style="text-align:center;margin:-8px 0 10px">Against Invoice: {{ doc.return_against }}</div>{% endif %}

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
            <td class="v">{{ "%.2f"|format(frappe.utils.flt(doc.total)) }}</td>
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


PRINT_FORMAT_80MM_NAME = "VanSale Tax Invoice 80mm"

# Page size: Frappe ignores CSS @page — it reads wkhtmltopdf's page-width /
# page-height / margins from a `.print-format { ... }` rule in the rendered
# HTML (frappe.utils.pdf.read_options_from_html). The rule is emitted from the
# template itself so the roll length follows the receipt's content; a static
# "@page { size: 80mm auto }" (the old approach) produced an A4 page with the
# receipt in its top-left corner. Nothing is left in the Print Format's CSS.
_CSS_80MM = ""

# Dedicated thermal layout for a 72mm printable width (80mm roll, 4mm side
# margins). Tables, not flexbox: wkhtmltopdf's WebKit has no flex support, so
# the old flex rows lost their right-aligned numbers. Amounts on a return are
# printed as magnitudes under a CREDIT NOTE heading, matching the ZATCA QR
# (services/zatca_qr.py), which also encodes magnitudes for returns.
_HTML_80MM = r"""
{%- set company = frappe.get_doc("Company", doc.company) -%}
{%- set settings = None -%}
{%- if frappe.db.exists("DocType", "ZG Company Settings") -%}
  {%- set sname = frappe.db.get_value("ZG Company Settings", {"company": doc.company}, "name") -%}
  {%- if sname -%}{%- set settings = frappe.get_doc("ZG Company Settings", sname) -%}{%- endif -%}
{%- endif -%}
{%- set vat_no = (settings.tax_id if settings and settings.tax_id else company.tax_id) or "" -%}
{%- set cr = company.get("company_registration") or company.get("registration_details") or "" -%}
{%- set phone = company.phone_no or "" -%}
{%- set cust_tax = frappe.db.get_value("Customer", doc.customer, "tax_id") or "" -%}
{%- set is_ret = doc.get("is_return") -%}
{%- set sign = -1 if is_ret else 1 -%}
{%- set qr_uri = tlv_to_png_data_uri(doc.get("zatca_qr_base64")) if doc.get("zatca_qr_base64") else "" -%}
{%- set cur = doc.currency or company.default_currency or "" -%}
{#- Payments: POS rows on the invoice itself, else submitted Payment Entries
    allocated against it (the auto-created Cash payment). -#}
{%- set pays = [] -%}
{%- for p in (doc.get("payments") or []) -%}
  {%- if p.amount -%}{%- set _ = pays.append([p.mode_of_payment, p.amount]) -%}{%- endif -%}
{%- endfor -%}
{%- if not pays and not is_ret -%}
  {%- for r in frappe.get_all("Payment Entry Reference", filters={"reference_doctype": "Sales Invoice", "reference_name": doc.name, "docstatus": 1}, fields=["parent", "allocated_amount"]) -%}
    {%- set _ = pays.append([frappe.db.get_value("Payment Entry", r.parent, "mode_of_payment") or "Payment", r.allocated_amount]) -%}
  {%- endfor -%}
{%- endif -%}
{%- set taxes = (doc.taxes or [])|selectattr("tax_amount")|list -%}
{#- Roll length in mm: fixed blocks + one estimate per item/tax/payment row,
    with a line per ~30 characters of item name. Generous on purpose — a short
    blank tail is better than a receipt split over two pages. -#}
{%- set ns = namespace(h=90) -%}
{%- for item in doc.items -%}
  {%- set ns.h = ns.h + 5 + 4 * (((item.item_name or item.item_code)|length) // 30 + 1) -%}
{%- endfor -%}
{%- set ns.h = ns.h + 5 * (taxes|length) + 5 * (pays|length) -%}
{%- if doc.discount_amount -%}{%- set ns.h = ns.h + 10 -%}{%- endif -%}
{%- if doc.get("rounding_adjustment") -%}{%- set ns.h = ns.h + 10 -%}{%- endif -%}
{%- if qr_uri -%}{%- set ns.h = ns.h + 34 -%}{%- endif -%}
{%- macro amt(v) -%}{{ "{:,.2f}".format(sign * frappe.utils.flt(v)) }}{%- endmacro -%}
<style>
  .print-format {
    page-width: 80mm; page-height: {{ ns.h }}mm;
    margin-top: 2mm; margin-bottom: 2mm; margin-left: 4mm; margin-right: 4mm;
    padding: 0 !important; width: auto !important; max-width: none !important;
  }
  .letter-head, .letter-head-footer { display: none !important; }
  .t80 { font-family: DejaVu Sans, Arial, sans-serif; font-size: 11px; color: #000; width: 100%; line-height: 1.3; }
  .t80 .c { text-align: center; }
  .t80 .b { font-weight: 700; }
  .t80 .co { font-size: 15px; font-weight: 700; }
  .t80 .ttl { font-size: 13px; font-weight: 700; margin-top: 3px; }
  .t80 .ar { direction: rtl; }
  .t80 hr { border: none; border-top: 1px dashed #000; margin: 4px 0; }
  .t80 table { width: 100%; border-collapse: collapse; table-layout: fixed; margin: 0 !important; }
  /* !important: Frappe's print stylesheet pads table cells for A4. */
  .t80 td, .t80 th { padding: 1px 0 !important; border: none !important; vertical-align: top; font-size: 11px; line-height: 1.3; }
  .t80 th { font-weight: 700; text-align: left; color: #000 !important; background: none !important; }
  .t80 .r { text-align: right; white-space: nowrap; }
  .t80 .nm { word-wrap: break-word; overflow-wrap: break-word; padding-top: 3px !important; }
  .t80 .meta td.k { width: 30%; }
  .t80 .grand td { font-size: 14px; font-weight: 700; padding-top: 3px !important; }
  .t80 .qr { text-align: center; margin-top: 6px; }
  .t80 .qr img { width: 30mm; height: 30mm; }
  .t80 .foot { text-align: center; font-size: 10px; margin-top: 4px; }
</style>
<div class="t80">
  <div class="c co">{{ company.company_name }}</div>
  {% if vat_no %}<div class="c">VAT: {{ vat_no }}</div>{% endif %}
  {% if cr %}<div class="c">CR: {{ cr }}</div>{% endif %}
  {% if phone %}<div class="c">Phone: {{ phone }}</div>{% endif %}
  <hr/>
  <div class="c ttl">{{ "CREDIT NOTE" if is_ret else "SIMPLIFIED TAX INVOICE" }}</div>
  <div class="c b ar">{{ "إشعار دائن" if is_ret else "فاتورة ضريبية مبسطة" }}</div>
  <hr/>
  <table class="meta">
    <tr><td class="k">{{ "Credit Note" if is_ret else "Invoice" }}</td><td class="b">{{ doc.name }}</td></tr>
    {% if is_ret and doc.get("return_against") %}<tr><td class="k">Against</td><td>{{ doc.return_against }}</td></tr>{% endif %}
    <tr><td class="k">Date</td><td>{{ frappe.utils.formatdate(doc.posting_date, "dd/MM/yyyy") }}{% if doc.get("posting_time") %} {{ frappe.utils.format_time(doc.posting_time, "HH:mm") }}{% endif %}</td></tr>
    <tr><td class="k">Customer</td><td>{{ doc.customer_name or doc.customer }}</td></tr>
    {% if cust_tax %}<tr><td class="k">VAT</td><td>{{ cust_tax }}</td></tr>{% endif %}
  </table>
  <hr/>
  <table>
    <colgroup><col style="width:34%"/><col style="width:30%"/><col style="width:36%"/></colgroup>
    <tr><th>QTY</th><th class="r">PRICE</th><th class="r">AMOUNT</th></tr>
  </table>
  <hr/>
  <table>
    <colgroup><col style="width:34%"/><col style="width:30%"/><col style="width:36%"/></colgroup>
    {% for item in doc.items %}
    <tr><td colspan="3" class="nm">{{ item.item_name or item.item_code }}</td></tr>
    <tr>
      {%- set q = sign * frappe.utils.flt(item.qty) -%}
      <td>{{ q|int if q == q|int else "%.2f"|format(q) }} {{ item.uom or "" }}</td>
      <td class="r">{{ "{:,.2f}".format(frappe.utils.flt(item.rate)) }}</td>
      <td class="r">{{ amt(item.amount) }}</td>
    </tr>
    {% endfor %}
  </table>
  <hr/>
  <table>
    <colgroup><col style="width:62%"/><col style="width:38%"/></colgroup>
    <tr><td>Subtotal</td><td class="r">{{ amt(doc.total) }}</td></tr>
    {% if doc.discount_amount %}
    <tr><td>Discount{% if doc.get("additional_discount_percentage") %} ({{ frappe.utils.flt(doc.additional_discount_percentage)|round(2) }}%){% endif %}</td><td class="r">-{{ amt(doc.discount_amount) }}</td></tr>
    <tr><td>Net Total</td><td class="r">{{ amt(doc.net_total) }}</td></tr>
    {% endif %}
    {% for t in taxes %}
    <tr><td>{{ t.description or t.account_head }}{% if t.rate and "%" not in (t.description or "") %} {{ frappe.utils.flt(t.rate)|round(2) }}%{% endif %}</td><td class="r">{{ amt(t.tax_amount_after_discount_amount or t.tax_amount) }}</td></tr>
    {% endfor %}
    <tr class="grand"><td>TOTAL {{ cur }}</td><td class="r">{{ amt(doc.grand_total) }}</td></tr>
    {% if doc.get("rounding_adjustment") %}
    <tr><td>Rounding</td><td class="r">{{ amt(doc.rounding_adjustment) }}</td></tr>
    <tr class="b"><td>Rounded Total</td><td class="r">{{ amt(doc.rounded_total) }}</td></tr>
    {% endif %}
  </table>
  <hr/>
  <table>
    <colgroup><col style="width:62%"/><col style="width:38%"/></colgroup>
    {% if is_ret %}
    <tr class="b"><td>Credit Balance</td><td class="r">{{ amt(doc.outstanding_amount) }}</td></tr>
    {% else %}
    {% if doc.get("custom_payment_type") %}<tr><td>Payment</td><td class="r b">{{ doc.custom_payment_type|upper }}</td></tr>{% endif %}
    {% for p in pays %}<tr><td>Paid ({{ p[0] }})</td><td class="r">{{ amt(p[1]) }}</td></tr>{% endfor %}
    <tr class="b"><td>Balance Due</td><td class="r">{{ amt(doc.outstanding_amount) }}</td></tr>
    {% endif %}
  </table>
  {% if qr_uri %}
  <div class="qr"><img src="{{ qr_uri }}" alt="QR"/></div>
  {% endif %}
  <hr/>
  <div class="foot b">Thank You &middot; شكراً لكم</div>
</div>
"""


DEMO_TAX_INVOICE_NAME = "Sales ZG1"

# Bilingual EN/AR tax invoice, built live in Desk against a real submitted
# invoice on democompanysa and iterated until it matched the reference
# design exactly (see project memory / session notes) -- captured here
# verbatim from production rather than re-authored, so this stays the
# single source of truth instead of drifting from what's actually live.
# Uses the vansale_* computed fields from patches/v0_2_1 (per-line VAT
# split, amount-in-words, running balance, bank details, signature) --
# see events/print_fields.py for how those get populated.
#
# Re-synced 2026-09-22 from what was actually live on democompanysa (it had
# drifted from this file -- title said "ORDER FORM" not "SALES", the
# balance box showed "Due Balance" instead of "New Balance", header markup
# had changed -- none of that was re-authored here, it was pulled verbatim
# off the live Print Format doc so this stays truthful to what prints).
# custom_payment_type badge (patches/v0_2_2/add_payment_type_field.py)
# added into the ORDER FORM meta bar in the same pass.
_DEMO_TAX_INVOICE_HTML = r"""  {# ERPNext / Frappe Print Format: Saudi VAT Tax — bilingual English + Arabic
     Order Form. Uses the vansale_* fields already deployed and verified on this site. #}
  {% set company = frappe.get_doc("Company", doc.company) %}
  {% set customer = frappe.get_doc("Customer", doc.customer) if doc.customer else none %}
  {% set customer_address = frappe.db.get_value("Address", {"name": doc.customer_address}, ["address_line1","address_line2","city","country"], as_dict=True) if doc.customer_address else none %}
  {% set company_address = frappe.db.get_value("Address", {"name": doc.company_address}, ["address_line1","address_line2","city","country"], as_dict=True) if doc.company_address else none %}

  <div class="invoice-page">

    <div class="company-header">
      <!-- The element sits directly in the header grid container to allow grid-column spanning -->
      <div class="company-name">{{ company.company_name or doc.company }}</div>
      
      <div class="header-left">
        {% if company.company_logo %}<img class="company-logo" src="{{ company.company_logo }}">{% endif %}
      </div>
    </div>

    <div class="invoice-meta-bar">
      <div>ORDER FORM <span class="arabic"> نموذج الطلب</span>{% if doc.custom_payment_type == "Cash" %}<span class="payment-type cash">CASH</span>{% elif doc.custom_payment_type == "Bank" %}<span class="payment-type bank">BANK</span>{% elif doc.custom_payment_type == "Credit" %}<span class="payment-type credit">CREDIT</span>{% endif %}</div>
      <div class="meta-grid">
        <div><span>No.</span><b>{{ doc.name }}</b></div>
        <div><span class="arabic">تاريخ مبيعات</span><b>{{ frappe.format_date(doc.posting_date) }}</b></div>
      </div>
    </div>

    <div class="buyer-box">
      <div class="section-title"><span>Buyer Details</span><span class="arabic">بيانات المشتري</span></div>
      <div class="buyer-grid">
        <div>
          <div class="label">Customer Name</div>
          <div class="value">{{ doc.customer_name or doc.customer }}</div>
          <div class="label">Address</div>
          <div class="value">
            {% if customer_address %}{{ customer_address.address_line1 or "" }}{% if customer_address.city %}, {{ customer_address.city }}{% endif %}{% else %}{{ doc.address_display or "" }}{% endif %}
          </div>
        </div>
        <div>
          <div class="label">Voucher No.</div>
          <div class="value">{{ doc.name }}</div>
        </div>
        <div>
          <div class="label">User</div>
          <div class="value">{{ frappe.db.get_value("User", doc.owner, "full_name") or doc.owner }}</div>
          <div class="label">Sales Person</div>
          <div class="value">{{ doc.sales_partner or "—" }}</div>
        </div>
        <div>
          <div class="label">Customer VAT No.</div>
          <div class="value">{{ (customer.tax_id if customer else "") or "" }}</div>
          <div class="label">Currency</div>
          <div class="value">{{ doc.currency or "SAR" }}</div>
        </div>
      </div>
    </div>

    <div class="items-section">
      <table class="items-table">
        <thead>
          <tr>
            <th class="no">No.<span class="arabic">م</span></th>
            <th class="code">Code<span class="arabic">الرمز</span></th>
            <th class="description">Description<span class="arabic">الوصف</span></th>
            <th class="qty">Qty<span class="arabic">الكمية</span></th>
            <th class="unit">Unit<span class="arabic">الوحدة</span></th>
            <th class="price">Unit Price<span class="arabic">سعر الوحدة</span></th>
            <th class="amount">Total Price<span class="arabic">السعر الإجمالي</span></th>
            <th class="vatpct">% VAT<span class="arabic">نسبة الضريبة</span></th>
            <th class="vatamt">VAT Amt<span class="arabic">مبلغ الضريبة</span></th>
            <th class="grand">Total<span class="arabic">الإجمالي</span></th>
          </tr>
        </thead>
        <tbody>
          {% for item in doc.items %}
          <tr>
            <td class="center">{{ loop.index }}</td>
            <td class="center">{{ item.item_code or "" }}</td>
            <td class="item-description">
              <div class="en">{{ item.item_name or "" }}</div>
              {% if item.description and item.description != item.item_name %}
                <div class="sub-description">{{ item.description }}</div>
              {% endif %}
            </td>
            <td class="num">{{ frappe.format(item.qty, {"fieldtype":"Float"}) }}</td>
            <td class="center">{{ item.uom or item.stock_uom or "" }}</td>
            <td class="num">{{ frappe.utils.fmt_money(item.rate, currency=doc.currency) }}</td>
            <td class="num">{{ frappe.utils.fmt_money(item.net_amount, currency=doc.currency) }}</td>
            <td class="num">{{ frappe.format(item.vansale_line_vat_rate, {"fieldtype":"Percent"}) }}</td>
            <td class="num">{{ frappe.utils.fmt_money(item.vansale_line_vat_amount, currency=doc.currency) }}</td>
            <td class="num">{{ frappe.utils.fmt_money(item.vansale_line_total_incl_vat, currency=doc.currency) }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <div class="bottom-grid">
      <div class="amount-area">
        <div class="words-title">Amount in Words <span class="arabic">المبلغ بالحروف</span></div>
        <div class="words">{{ doc.vansale_amount_in_words_print or "" }}</div>
       <div class="balance-box">
  <div>
    <span>Previous Balance <span class="arabic">الرصيد السابق</span></span>
    <b>{{ frappe.utils.fmt_money(doc.vansale_previous_balance or 0, currency=doc.currency) }}</b>
  </div>
  <div>
    <span>Due Balance <span class="arabic">الرصيد المستحق</span></span>
    {# Formula calculation: Previous Balance + Grand Total - Paid Amount #}
    {% set dynamic_due_balance = (doc.vansale_previous_balance or 0) + (doc.grand_total or 0) - (doc.paid_amount or 0) %}
    <b>{{ frappe.utils.fmt_money(dynamic_due_balance, currency=doc.currency) }}</b>
  </div>
</div>

      <div class="totals-area">
        <div class="total-row"><span>TOTAL AMOUNT <small class="arabic">الإجمالي</small></span><b>{{ frappe.utils.fmt_money(doc.net_total, currency=doc.currency) }}</b></div>
        <div class="total-row"><span>DISCOUNT <small class="arabic">الخصم</small></span><b>{{ frappe.utils.fmt_money(doc.discount_amount or 0, currency=doc.currency) }}</b></div>
        
        <div class="grand-row"><span>GRAND TOTAL <small class="arabic">الإجمالي النهائي</small></span><b>{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</b></div>
      </div>
    </div>

    <div class="footer-grid">
      <div class="bank-area">
        <div class="bank-title">Bank Details <span class="arabic">بيانات البنك</span></div>
        {% if company.vansale_bank_1_name %}
        <div class="bank-row"><b>{{ company.vansale_bank_1_name }}</b><span>Account No. {{ company.vansale_bank_1_account or "" }}</span><span>IBAN: {{ company.vansale_bank_1_iban or "" }}</span></div>
        {% endif %}
        {% if company.vansale_bank_2_name %}
        <div class="bank-row"><b>{{ company.vansale_bank_2_name }}</b><span>Account No. {{ company.vansale_bank_2_account or "" }}</span><span>IBAN: {{ company.vansale_bank_2_iban or "" }}</span></div>
        {% endif %}
      </div>
    </div>

    <div class="signature-row">
      <div>
        {% if doc.vansale_authorized_signature %}<img src="{{ doc.vansale_authorized_signature }}" style="max-height:10mm;">{% endif %}
        <div class="signature-line"></div>
        Received By <span class="arabic">المستلم</span>
      </div>
      <div>
        <div class="signature-line"></div>
        Salesman <span class="arabic">البائع</span>
      </div>
    </div>

    <div class="page-footer">
      <span>Page {{ page_number or 1 }} of {{ total_pages or 1 }}</span>
      <span>{{ doc.company }}</span>
    </div>

  </div>
"""

_DEMO_TAX_INVOICE_CSS = r"""
/* =========================================================
   ZatGo / ERPNext — Saudi VAT Tax Invoice
   A4 portrait, bilingual English + Arabic
   No external libraries required.
   ========================================================= */

@page {
  size: A4 portrait;
  margin: 6mm 7mm 7mm 7mm;
}

* {
  box-sizing: border-box;
}

html, body {
  margin: 0 !important;
  padding: 0 !important;
  background: #fff !important;
  color: #111;
  font-family: Arial, "Noto Sans", sans-serif;
  font-size: 8.2pt;
  line-height: 1.18;
}

.invoice-page {
  width: 100%;
  max-width: 196mm;
  margin: 0 auto;
}

/* ---------- Typography ---------- */

.arabic {
  direction: rtl;
  font-family: "Noto Naskh Arabic", "Noto Sans Arabic", Tahoma, Arial, sans-serif;
}

/* ---------- Typography Updates ---------- */

.company-name,
.company-name-ar {
  font-size: 24pt;
  font-weight: 1200;
  letter-spacing: .1px;
  text-transform: uppercase;
  text-align: center;
  
  /* Core Fixes for Precise Grid Centering */
  grid-column: 1 / -1;   /* Spans across all 3 grid columns completely */
  width: 100%;           /* Ensures text aligns relative to full page container */
  margin: 0 auto;        /* Safeguards margin spacing layout uniformities */
}


.company-meta {
  font-size: 12pt;
  line-height: 1.25;
  margin-top: 1.5mm;
}

/* ---------- Header ---------- */

.company-header {
  min-height: 32mm;
  border: .45mm solid #8d9da5;
  border-radius: 1.5mm 1.5mm 0 0;
  display: grid;
  grid-template-columns: 42% 16% 42%;
  align-items: center;
  padding: 3mm 4mm;
  background: linear-gradient(to bottom, #f7fbfc, #fff);
}

.header-left {
  text-align: left;
}

.header-center {
  display: flex;
  justify-content: center;
  align-items: center;
}

.header-right {
  text-align: right;
}

.company-logo {
  max-width: 37mm;
  max-height: 12mm;
  object-fit: contain;
  display: block;
  margin-bottom: 1.5mm;
}

.brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1mm;
  font-weight: 900;
  font-size: 13pt;
  color: #244d5a;
}

.brand-circle {
  width: 11mm;
  height: 11mm;
  border: 1mm solid #5c8c98;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10pt;
}

.brand-text {
  letter-spacing: .5px;
}

/* ---------- Invoice meta ---------- */

.invoice-meta-bar {
  min-height: 11mm;
  border: .45mm solid #6c8b96;
  border-top: 0;
  display: grid;
  grid-template-columns: 45% 55%;
  align-items: center;
  background: #edf6f8;
  padding: 1.5mm 3mm;
}

.invoice-meta-bar > div:first-child {
  font-size: 9.5pt;
  display: flex;
  gap: 5mm;
  align-items: center;
}

.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2mm;
}

.meta-grid > div {
  display: flex;
  justify-content: space-between;
  gap: 2mm;
  border-left: .25mm solid #aab9be;
  padding-left: 2mm;
}

.meta-grid span {
  color: #444;
}

/* ---------- Buyer ---------- */

.buyer-box {
  border: .45mm solid #718f98;
  border-top: 0;
}

.section-title {
  height: 6.5mm;
  padding: 1.2mm 2.5mm;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 800;
  background: #dceef2;
  border-bottom: .3mm solid #7d9ba4;
}

.buyer-grid {
  display: grid;
  grid-template-columns: 31% 23% 23% 23%;
  min-height: 23mm;
}

.buyer-grid > div {
  padding: 2mm 2.5mm;
  border-right: .25mm solid #a9b7bb;
}

.buyer-grid > div:last-child {
  border-right: 0;
}

.label {
  font-size: 6.8pt;
  color: #555;
  margin-bottom: .5mm;
}

.value {
  font-weight: 700;
  min-height: 4mm;
  margin-bottom: 1.4mm;
}

/* ---------- Items ---------- */

.items-section {
  margin-top: 0;
}

.items-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.items-table th,
.items-table td {
  border: .3mm solid #7f9299;
  padding: 1.1mm .9mm;
  vertical-align: middle;
}

.items-table thead th {
  background: #d7e9ed;
  text-align: center;
  font-size: 6.8pt;
  line-height: 1.15;
  font-weight: 800;
}

.items-table thead th .arabic {
  display: block;
  margin-top: .6mm;
  font-size: 6.5pt;
  font-weight: 700;
}

.items-table tbody td {
  font-size: 7.2pt;
}

.items-table .no { width: 5%; }
.items-table .code { width: 9%; }
.items-table .description { width: 24%; }
.items-table .qty { width: 7%; }
.items-table .unit { width: 7%; }
.items-table .price { width: 10%; }
.items-table .amount { width: 10%; }
.items-table .vatpct { width: 7%; }
.items-table .vatamt { width: 9%; }
.items-table .grand { width: 12%; }

.center {
  text-align: center;
}

.num {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.item-description {
  text-align: left;
  word-wrap: break-word;
}

.item-description .en {
  font-weight: 600;
}

.sub-description {
  margin-top: .8mm;
  font-size: 6.2pt;
  color: #444;
}

.items-table tbody tr {
  height: 11mm;
}

/* Keep rows together in PDF/print output */
.items-table tr {
  break-inside: avoid;
  page-break-inside: avoid;
}

/* ---------- Bottom totals ---------- */

.bottom-grid {
  display: grid;
  grid-template-columns: 58% 42%;
  border-left: .3mm solid #7f9299;
  border-right: .3mm solid #7f9299;
  border-bottom: .3mm solid #7f9299;
}

.amount-area {
  padding: 2.5mm 3mm;
  min-height: 38mm;
  border-right: .3mm solid #7f9299;
}

.words-title {
  font-weight: 800;
  margin-bottom: 1mm;
}

.words {
  font-weight: 700;
  line-height: 1.35;
}

.words-arabic {
  margin-top: 1.5mm;
  font-weight: 600;
}

.balance-box {
  margin-top: 3mm;
  width: 70%;
  border-top: .25mm solid #9aa8ac;
}

.balance-box > div {
  display: flex;
  justify-content: space-between;
  padding: 1mm 0;
  border-bottom: .25mm solid #d2d7d9;
}

.totals-area {
  padding: 0;
}

.total-row,
.grand-row {
  display: grid;
  grid-template-columns: 66% 34%;
  min-height: 8mm;
  border-bottom: .3mm solid #7f9299;
}

.total-row span,
.grand-row span {
  padding: 1.2mm 2mm;
  font-size: 7pt;
  font-weight: 800;
}

.total-row b,
.grand-row b {
  padding: 1.2mm 2mm;
  text-align: right;
  border-left: .3mm solid #7f9299;
  font-size: 8pt;
}

.total-row small,
.grand-row small {
  font-size: 6.2pt;
  font-weight: 600;
}

.grand-row {
  min-height: 10mm;
  border-bottom: 0;
  background: #dceef2;
}

.grand-row span,
.grand-row b {
  font-size: 8.5pt;
  font-weight: 900;
}

/* ---------- Footer / QR / Bank ---------- */

.footer-grid {
  display: grid;
  grid-template-columns: 28% 72%;
  min-height: 31mm;
  border: .3mm solid #7f9299;
  border-top: 0;
}

.qr-area {
  padding: 2mm;
  border-right: .3mm solid #7f9299;
  text-align: center;
}

.qr-code {
  width: 25mm;
  height: 25mm;
  object-fit: contain;
  display: block;
  margin: 0 auto 1mm;
}

.qr-caption {
  font-size: 6.2pt;
}

.bank-area {
  padding: 2mm 3mm;
}

.bank-title {
  font-weight: 900;
  font-size: 8pt;
  padding-bottom: 1.5mm;
  border-bottom: .3mm solid #8fa1a7;
}

.bank-title .arabic {
  float: right;
}

.bank-row {
  display: grid;
  grid-template-columns: 18% 31% 51%;
  align-items: center;
  min-height: 9mm;
  border-bottom: .25mm solid #d3d9db;
  font-size: 7pt;
}

.bank-row:last-child {
  border-bottom: 0;
}

.bank-row b {
  font-size: 7.5pt;
}

/* ---------- Signatures ---------- */

.signature-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18mm;
  margin-top: 7mm;
  font-size: 7pt;
}

.signature-row > div {
  position: relative;
  min-height: 10mm;
}

.signature-line {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  border-bottom: .25mm solid #555;
}

/* ---------- Page footer ---------- */

.page-footer {
  display: flex;
  justify-content: center;
  gap: 35mm;
  margin-top: 3mm;
  font-size: 6.5pt;
  color: #555;
}

/* ---------- Print behavior ---------- */

@media print {
  body {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }

  .invoice-page {
    page-break-after: auto;
  }

  .items-table thead {
    display: table-header-group;
  }

  .items-table tfoot {
    display: table-footer-group;
  }

  .items-table tr,
  .buyer-box,
  .bottom-grid,
  .footer-grid,
  .signature-row {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }
}

/* ---------- Compact mode for invoices with many rows ---------- */

.compact-invoice .items-table tbody td {
  padding-top: .7mm;
  padding-bottom: .7mm;
}

.compact-invoice .items-table tbody tr {
  height: 8mm;
}

/* ---------- Payment Type badge ---------- */
.payment-type {
  display: inline-block;
  margin-left: 3mm;
  padding: 0.6mm 2.4mm;
  border-radius: 1mm;
  font-size: 7pt;
  font-weight: 800;
  letter-spacing: .3px;
  color: #fff;
  vertical-align: middle;
}

.payment-type.cash {
  background: #15803d;
}

.payment-type.bank {
  background: #1d4ed8;
}

.payment-type.credit {
  background: #b45309;
}
"""

QUOTATION_PRINT_FORMAT_NAME = "ZatGo Quotation"

# Professional proposal-style quotation: brand-green accent, prepared-for/by
# boxes, itemized commercials table, terms, signature blocks. All content is
# pulled from the Quotation doc / Company / Customer — nothing hardcoded per
# company, so this works for any tenant using this print format.
_QUOTATION_HTML = r"""
<style>
  .zq { font-family: DejaVu Sans, Arial, sans-serif; font-size: 11px; color: #1f2937; }
  .zq * { box-sizing: border-box; }
  .zq-accent { color: #15803d; }
  .zq-head { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
  .zq-head td { vertical-align: top; }
  .zq-logo img { max-height: 60px; max-width: 180px; }
  .zq-company-name { font-weight: 700; font-size: 13px; }
  .zq-title { text-align: right; font-size: 26px; font-weight: 700; color: #15803d; margin: 0; }
  .zq-meta { text-align: right; font-size: 10px; color: #4b5563; margin-top: 4px; }
  .zq-meta b { color: #1f2937; }
  .zq-tagline { font-size: 10px; font-weight: 700; color: #374151; margin: 10px 0 12px; }
  .zq-boxes { width: 100%; border-collapse: collapse; margin-bottom: 14px; }
  .zq-boxes td { width: 50%; padding: 10px 12px; vertical-align: top; }
  .zq-boxes .for { background: #f3f4f6; }
  .zq-boxes .by { background: #ecfdf5; }
  .zq-box-label { font-size: 9px; font-weight: 700; letter-spacing: 0.04em; color: #15803d; margin-bottom: 4px; }
  .zq-box-name { font-size: 13px; font-weight: 700; margin-bottom: 4px; }
  .zq-section-label {
    font-size: 11px; font-weight: 700; border-left: 3px solid #15803d; padding-left: 6px; margin: 14px 0 8px;
  }
  .zq-table { width: 100%; border-collapse: collapse; margin-top: 4px; }
  .zq-table th { background: #15803d; color: #fff; text-align: left; padding: 6px 8px; font-size: 10px; }
  .zq-table th.num, .zq-table td.num { text-align: right; }
  .zq-table td { padding: 8px; border-bottom: 1px solid #e5e7eb; font-size: 10.5px; vertical-align: top; }
  .zq-table .item-name { font-weight: 700; }
  .zq-table .item-desc { color: #6b7280; font-size: 9.5px; }
  .zq-totals { width: 100%; border-collapse: collapse; margin-top: 12px; }
  .zq-totals td { padding: 10px 12px; }
  .zq-totals .grand { background: #ecfdf5; border-top: 2px solid #15803d; }
  .zq-totals .grand-label { font-size: 9px; font-weight: 700; letter-spacing: 0.04em; color: #15803d; }
  .zq-totals .grand-value { font-size: 16px; font-weight: 700; color: #15803d; }
  .zq-terms { font-size: 10px; line-height: 1.5; color: #374151; }
  .zq-sign { width: 100%; border-collapse: collapse; margin-top: 26px; }
  .zq-sign td { width: 50%; padding-top: 26px; border-top: 1px solid #9ca3af; font-size: 10px; }
  .zq-sign .lbl { font-size: 9px; color: #6b7280; }
  .zq-footer { margin-top: 18px; text-align: center; font-size: 8.5px; color: #9ca3af; border-top: 1px solid #e5e7eb; padding-top: 6px; }
</style>
{%- set company = frappe.get_doc("Company", doc.company) -%}
{%- set customer = frappe.get_doc("Customer", doc.party_name) if doc.quotation_to == "Customer" else None -%}
{%- set logo_url = company.company_logo -%}

<div class="zq">
  <table class="zq-head">
    <tr>
      <td style="width:55%">
        {% if logo_url %}
        <div class="zq-logo"><img src="{{ logo_url }}" alt="{{ company.company_name }}"/></div>
        {% else %}
        <div class="zq-company-name">{{ company.company_name }}</div>
        {% endif %}
      </td>
      <td style="width:45%">
        <p class="zq-title">QUOTATION</p>
        <div class="zq-meta">
          <div>Ref: <b>#{{ doc.name }}</b></div>
          <div>Date: <b>{{ frappe.utils.formatdate(doc.transaction_date, "dd MMM yyyy") }}</b></div>
          {% if doc.valid_till %}<div>Valid: <b>{{ frappe.utils.formatdate(doc.valid_till, "dd MMM yyyy") }}</b></div>{% endif %}
        </div>
      </td>
    </tr>
  </table>

  <table class="zq-boxes">
    <tr>
      <td class="for">
        <div class="zq-box-label">PREPARED FOR</div>
        <div class="zq-box-name">{{ doc.customer_name or doc.party_name }}</div>
        {% if customer and customer.customer_primary_contact %}<div>{{ customer.customer_primary_contact }}</div>{% endif %}
      </td>
      <td class="by">
        <div class="zq-box-label">PREPARED BY</div>
        <div class="zq-box-name">{{ company.company_name }}</div>
        {% if company.email %}<div>Email: {{ company.email }}</div>{% endif %}
        {% if company.phone_no %}<div>Phone: {{ company.phone_no }}</div>{% endif %}
        {% if company.website %}<div>Web: {{ company.website }}</div>{% endif %}
      </td>
    </tr>
  </table>

  <div class="zq-section-label">COMMERCIALS</div>
  <table class="zq-table">
    <thead>
      <tr>
        <th style="width:6%">#</th>
        <th style="width:54%">Description</th>
        <th style="width:20%">Type</th>
        <th class="num" style="width:20%">Amount</th>
      </tr>
    </thead>
    <tbody>
      {% for item in doc.items %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>
          <div class="item-name">{{ item.item_name or item.item_code }}</div>
          {% if item.description and item.description != (item.item_name or item.item_code) %}
          <div class="item-desc">{{ item.description | striptags }}</div>
          {% endif %}
        </td>
        <td>{{ item.zatgo_billing_type or "—" }}</td>
        <td class="num">{{ doc.currency }} {{ "{:,.2f}".format(frappe.utils.flt(item.amount)) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <table class="zq-totals">
    <tr>
      <td style="width:60%"></td>
      <td class="grand" style="width:40%">
        <div class="grand-label">GRAND TOTAL</div>
        <div class="grand-value">{{ doc.currency }} {{ "{:,.2f}".format(frappe.utils.flt(doc.grand_total)) }}</div>
      </td>
    </tr>
  </table>

  {% if doc.terms %}
  <div class="zq-section-label">TERMS &amp; CONDITIONS</div>
  <div class="zq-terms">{{ doc.terms }}</div>
  {% endif %}

  <table class="zq-sign">
    <tr>
      <td>
        <div class="zq-box-name">{{ company.company_name }}</div>
        <div class="lbl">AUTHORIZED SIGNATORY</div>
      </td>
      <td>
        <div class="zq-box-name">{{ doc.customer_name or doc.party_name }}</div>
        <div class="lbl">CLIENT ACCEPTANCE / CONFIRMATION</div>
      </td>
    </tr>
  </table>

  <div class="zq-footer">{{ company.company_name }} &nbsp;|&nbsp; Quotation #{{ doc.name }} &nbsp;|&nbsp; Confidential</div>
</div>
"""


DEMO_QUOTATION_EN_NAME = "Quotation (EN)"
DEMO_QUOTATION_AR_NAME = "Quotation (AR)"
DEMO_DELIVERY_NOTE_EN_NAME = "Delivery Note (EN)"
DEMO_DELIVERY_NOTE_AR_NAME = "Delivery Note (AR)"

# Shared A4 stylesheet for the Quotation/Delivery Note family below -- same
# visual identity as Sales ZG1 (bordered header/meta/buyer-box/items-table)
# but trimmed of VAT/QR/bank sections these doctypes don't carry. RTL
# mirroring is done via [dir="rtl"] attribute overrides in one stylesheet
# rather than a duplicated CSS file per language.
_QUOTE_DN_CSS = r"""
@page {
  size: A4 portrait;
  margin: 6mm 7mm 7mm 7mm;
}

* {
  box-sizing: border-box;
}

html, body {
  margin: 0 !important;
  padding: 0 !important;
  background: #fff !important;
  color: #111;
  font-family: Arial, "Noto Sans", sans-serif;
  font-size: 9pt;
  line-height: 1.25;
}

.invoice-page {
  width: 100%;
  max-width: 196mm;
  margin: 0 auto;
}

.invoice-page[dir="rtl"] {
  font-family: "Noto Naskh Arabic", "Noto Sans Arabic", Tahoma, Arial, sans-serif;
}

.company-header {
  min-height: 26mm;
  border: .45mm solid #8d9da5;
  border-radius: 1.5mm 1.5mm 0 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3mm 4mm;
  background: linear-gradient(to bottom, #f7fbfc, #fff);
}

.company-logo {
  max-width: 40mm;
  max-height: 14mm;
  object-fit: contain;
  display: block;
  margin-bottom: 1.5mm;
}

.company-name {
  font-size: 12pt;
  font-weight: 800;
}

.company-meta {
  font-size: 7.5pt;
  line-height: 1.3;
  margin-top: 1.5mm;
  color: #444;
}

.invoice-meta-bar {
  min-height: 11mm;
  border: .45mm solid #6c8b96;
  border-top: 0;
  display: grid;
  grid-template-columns: 40% 60%;
  align-items: center;
  background: #edf6f8;
  padding: 1.5mm 3mm;
}

.invoice-meta-bar .doc-title {
  font-size: 11pt;
  font-weight: 800;
}

.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 2mm;
}

.meta-grid > div {
  border-left: .25mm solid #aab9be;
  padding-left: 2mm;
}
[dir="rtl"] .meta-grid > div {
  border-left: none;
  border-right: .25mm solid #aab9be;
  padding-left: 0;
  padding-right: 2mm;
}

.meta-grid .k {
  font-size: 7pt;
  color: #555;
}
.meta-grid .v {
  font-weight: 700;
}

.buyer-box {
  border: .45mm solid #718f98;
  border-top: 0;
}

.section-title {
  height: 6.5mm;
  padding: 1.2mm 2.5mm;
  display: flex;
  align-items: center;
  font-weight: 800;
  font-size: 9pt;
  background: #dceef2;
  border-bottom: .3mm solid #7d9ba4;
}

.buyer-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 14mm;
}

.buyer-grid > div {
  padding: 2mm 2.5mm;
}
.buyer-grid > div:first-child {
  border-right: .25mm solid #a9b7bb;
}
[dir="rtl"] .buyer-grid > div:first-child {
  border-right: none;
  border-left: .25mm solid #a9b7bb;
}

.label {
  font-size: 7pt;
  color: #555;
  margin-bottom: .5mm;
}

.value {
  font-weight: 700;
  min-height: 4mm;
  margin-bottom: 1.4mm;
}

.items-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  margin-top: 0;
}

.items-table th,
.items-table td {
  border: .3mm solid #7f9299;
  padding: 1.4mm 1.1mm;
  vertical-align: middle;
}

.items-table thead th {
  background: #42536b;
  color: #fff;
  text-align: center;
  font-size: 8pt;
  font-weight: 700;
}

.items-table tbody td {
  font-size: 8.2pt;
}

.items-table .no { width: 6%; }
.items-table .code { width: 12%; }
.items-table .description { width: 38%; }
.items-table .qty { width: 10%; }
.items-table .unit { width: 10%; }
.items-table .price { width: 12%; }
.items-table .amount { width: 12%; }

.center { text-align: center; }
.num {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
[dir="rtl"] .num { text-align: left; }

.item-description { text-align: left; word-wrap: break-word; }
[dir="rtl"] .item-description { text-align: right; }

.items-table tr {
  break-inside: avoid;
  page-break-inside: avoid;
}

.bottom-grid {
  display: grid;
  grid-template-columns: 55% 45%;
  border-left: .3mm solid #7f9299;
  border-right: .3mm solid #7f9299;
  border-bottom: .3mm solid #7f9299;
}

.terms-area {
  padding: 2.5mm 3mm;
  border-right: .3mm solid #7f9299;
  font-size: 8pt;
}
[dir="rtl"] .terms-area {
  border-right: none;
  border-left: .3mm solid #7f9299;
}

.terms-title {
  font-weight: 800;
  margin-bottom: 1mm;
}

.words {
  font-weight: 700;
  line-height: 1.4;
  margin-top: 2mm;
}

.total-row,
.grand-row {
  display: grid;
  grid-template-columns: 60% 40%;
  min-height: 8mm;
  border-bottom: .3mm solid #7f9299;
}

.total-row span,
.grand-row span {
  padding: 1.2mm 2mm;
  font-size: 8pt;
  font-weight: 700;
}

.total-row b,
.grand-row b {
  padding: 1.2mm 2mm;
  text-align: right;
  border-left: .3mm solid #7f9299;
  font-size: 8.5pt;
}
[dir="rtl"] .total-row b, [dir="rtl"] .grand-row b {
  text-align: left;
  border-left: none;
  border-right: .3mm solid #7f9299;
}

.grand-row {
  min-height: 10mm;
  border-bottom: 0;
  background: #dceef2;
}
.grand-row span, .grand-row b {
  font-size: 9pt;
  font-weight: 900;
}

.signature-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18mm;
  margin-top: 10mm;
  font-size: 8pt;
}

.signature-row > div {
  position: relative;
  min-height: 10mm;
  text-align: center;
}

.signature-line {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  border-bottom: .25mm solid #555;
}

.page-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 4mm;
  font-size: 7pt;
  color: #555;
}

@media print {
  body { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  .items-table thead { display: table-header-group; }
  .items-table tr, .buyer-box, .bottom-grid, .signature-row {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }
}
"""

_DEMO_QUOTATION_EN_HTML = r"""
{# ERPNext / Frappe Print Format: Quotation (EN) — company-agnostic, works on any site #}
{% set company = frappe.get_doc("Company", doc.company) %}
{% set words = frappe.utils.money_in_words(doc.grand_total or 0, doc.currency or company.default_currency) %}

<div class="invoice-page" dir="ltr">

  <div class="company-header">
    <div>
      {% if company.company_logo %}<img class="company-logo" src="{{ company.company_logo }}">{% endif %}
      <div class="company-name">{{ company.company_name or doc.company }}</div>
    </div>
    <div class="company-meta" style="text-align:right">
      {% if company.phone_no %}{{ company.phone_no }}<br>{% endif %}
      {% if company.email %}{{ company.email }}{% endif %}
    </div>
  </div>

  <div class="invoice-meta-bar">
    <div class="doc-title">QUOTATION</div>
    <div class="meta-grid">
      <div>
        <div class="k">Quotation No.</div>
        <div class="v">{{ doc.name }}</div>
      </div>
      <div>
        <div class="k">Date</div>
        <div class="v">{{ frappe.format_date(doc.get("transaction_date") or doc.get("posting_date")) }}</div>
      </div>
        <div>
          <div class="k">Valid Till</div>
          <div class="v">{{ frappe.format_date(doc.valid_till) if doc.valid_till else "—" }}</div>
        </div>
    </div>
  </div>

  <div class="buyer-box">
    <div class="section-title">Buyer Details</div>
    <div class="buyer-grid">
      <div>
        <div class="label">Customer Name</div>
        <div class="value">{{ doc.get("customer_name") or doc.party_name or doc.get("customer") or "" }}</div>
      </div>
      <div>
        <div class="label">Address</div>
        <div class="value">{% set _addr = frappe.db.get_value("Address", {"name": doc.customer_address}, ["address_line1","city"], as_dict=True) if doc.get("customer_address") else none %}
          {% if _addr %}{{ _addr.address_line1 or "" }}{% if _addr.city %}, {{ _addr.city }}{% endif %}{% else %}{{ doc.address_display or "" }}{% endif %}</div>
      </div>
    </div>
  </div>

  <table class="items-table">
    <thead>
      <tr>
        <th class="no">No.</th>
        <th class="code">Code</th>
        <th class="description">Description</th>
        <th class="qty">Qty</th>
        <th class="unit">Unit</th>
        <th class="price">Unit Price</th>
        <th class="amount">Amount</th>
      </tr>
    </thead>
    <tbody>
      {% for item in doc.items %}
      <tr>
        <td class="center">{{ loop.index }}</td>
        <td class="center">{{ item.item_code or "" }}</td>
        <td class="item-description">{{ item.item_name or "" }}</td>
        <td class="num">{{ frappe.format(item.qty, {"fieldtype":"Float"}) }}</td>
        <td class="center">{{ item.uom or item.stock_uom or "" }}</td>
        <td class="num">{{ frappe.utils.fmt_money(item.rate, currency=doc.currency) }}</td>
        <td class="num">{{ frappe.utils.fmt_money(item.amount, currency=doc.currency) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="bottom-grid">
    <div class="terms-area">
      {% if doc.get("tc_name") and doc.get("terms") %}
      <div class="terms-title">Terms &amp; Conditions</div>
      <div>{{ doc.terms }}</div>
      {% endif %}
      <div class="words"><b>Amount in Words:</b> {{ words }}</div>
    </div>
    <div>
      <div class="total-row"><span>Net Total</span><b>{{ frappe.utils.fmt_money(doc.net_total, currency=doc.currency) }}</b></div>
      <div class="total-row"><span>Tax</span><b>{{ frappe.utils.fmt_money(doc.total_taxes_and_charges or 0, currency=doc.currency) }}</b></div>
      <div class="grand-row"><span>Grand Total</span><b>{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</b></div>
    </div>
  </div>

  <div class="signature-row">
    <div>
      <div class="signature-line"></div>
      Received By
    </div>
    <div>
      <div class="signature-line"></div>
      Prepared By
    </div>
  </div>

  <div class="page-footer">
    <span>{{ company.company_name }}</span>
    <span>Page {{ page_number or 1 }} / {{ total_pages or 1 }}</span>
  </div>

</div>
"""

_DEMO_QUOTATION_AR_HTML = r"""
{# ERPNext / Frappe Print Format: Quotation (AR) — company-agnostic, works on any site #}
{% set company = frappe.get_doc("Company", doc.company) %}
{% set words = frappe.utils.money_in_words(doc.grand_total or 0, doc.currency or company.default_currency) %}

<div class="invoice-page" dir="rtl">

  <div class="company-header">
    <div>
      {% if company.company_logo %}<img class="company-logo" src="{{ company.company_logo }}">{% endif %}
      <div class="company-name">{{ company.company_name or doc.company }}</div>
    </div>
    <div class="company-meta" style="text-align:left">
      {% if company.phone_no %}{{ company.phone_no }}<br>{% endif %}
      {% if company.email %}{{ company.email }}{% endif %}
    </div>
  </div>

  <div class="invoice-meta-bar">
    <div class="doc-title">عرض سعر</div>
    <div class="meta-grid">
      <div>
        <div class="k">رقم العرض</div>
        <div class="v">{{ doc.name }}</div>
      </div>
      <div>
        <div class="k">التاريخ</div>
        <div class="v">{{ frappe.format_date(doc.get("transaction_date") or doc.get("posting_date")) }}</div>
      </div>
        <div>
          <div class="k">صالح حتى</div>
          <div class="v">{{ frappe.format_date(doc.valid_till) if doc.valid_till else "—" }}</div>
        </div>
    </div>
  </div>

  <div class="buyer-box">
    <div class="section-title">بيانات العميل</div>
    <div class="buyer-grid">
      <div>
        <div class="label">اسم العميل</div>
        <div class="value">{{ doc.get("customer_name") or doc.party_name or doc.get("customer") or "" }}</div>
      </div>
      <div>
        <div class="label">العنوان</div>
        <div class="value">{% set _addr = frappe.db.get_value("Address", {"name": doc.customer_address}, ["address_line1","city"], as_dict=True) if doc.get("customer_address") else none %}
          {% if _addr %}{{ _addr.address_line1 or "" }}{% if _addr.city %}, {{ _addr.city }}{% endif %}{% else %}{{ doc.address_display or "" }}{% endif %}</div>
      </div>
    </div>
  </div>

  <table class="items-table">
    <thead>
      <tr>
        <th class="no">م</th>
        <th class="code">الرمز</th>
        <th class="description">الوصف</th>
        <th class="qty">الكمية</th>
        <th class="unit">الوحدة</th>
        <th class="price">السعر</th>
        <th class="amount">المبلغ</th>
      </tr>
    </thead>
    <tbody>
      {% for item in doc.items %}
      <tr>
        <td class="center">{{ loop.index }}</td>
        <td class="center">{{ item.item_code or "" }}</td>
        <td class="item-description">{{ item.item_name or "" }}</td>
        <td class="num">{{ frappe.format(item.qty, {"fieldtype":"Float"}) }}</td>
        <td class="center">{{ item.uom or item.stock_uom or "" }}</td>
        <td class="num">{{ frappe.utils.fmt_money(item.rate, currency=doc.currency) }}</td>
        <td class="num">{{ frappe.utils.fmt_money(item.amount, currency=doc.currency) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="bottom-grid">
    <div class="terms-area">
      {% if doc.get("tc_name") and doc.get("terms") %}
      <div class="terms-title">الشروط والأحكام</div>
      <div>{{ doc.terms }}</div>
      {% endif %}
      <div class="words"><b>المبلغ بالحروف:</b> {{ words }}</div>
    </div>
    <div>
      <div class="total-row"><span>الإجمالي</span><b>{{ frappe.utils.fmt_money(doc.net_total, currency=doc.currency) }}</b></div>
      <div class="total-row"><span>الضريبة</span><b>{{ frappe.utils.fmt_money(doc.total_taxes_and_charges or 0, currency=doc.currency) }}</b></div>
      <div class="grand-row"><span>الإجمالي النهائي</span><b>{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</b></div>
    </div>
  </div>

  <div class="signature-row">
    <div>
      <div class="signature-line"></div>
      المستلم
    </div>
    <div>
      <div class="signature-line"></div>
      أعده
    </div>
  </div>

  <div class="page-footer">
    <span>{{ company.company_name }}</span>
    <span>صفحة {{ page_number or 1 }} / {{ total_pages or 1 }}</span>
  </div>

</div>
"""

_DEMO_DELIVERY_NOTE_EN_HTML = r"""
{# ERPNext / Frappe Print Format: Delivery Note (EN) — company-agnostic, works on any site #}
{% set company = frappe.get_doc("Company", doc.company) %}
{% set words = frappe.utils.money_in_words(doc.grand_total or 0, doc.currency or company.default_currency) %}

<div class="invoice-page" dir="ltr">

  <div class="company-header">
    <div>
      {% if company.company_logo %}<img class="company-logo" src="{{ company.company_logo }}">{% endif %}
      <div class="company-name">{{ company.company_name or doc.company }}</div>
    </div>
    <div class="company-meta" style="text-align:right">
      {% if company.phone_no %}{{ company.phone_no }}<br>{% endif %}
      {% if company.email %}{{ company.email }}{% endif %}
    </div>
  </div>

  <div class="invoice-meta-bar">
    <div class="doc-title">DELIVERY NOTE</div>
    <div class="meta-grid">
      <div>
        <div class="k">Delivery Note No.</div>
        <div class="v">{{ doc.name }}</div>
      </div>
      <div>
        <div class="k">Date</div>
        <div class="v">{{ frappe.format_date(doc.get("transaction_date") or doc.get("posting_date")) }}</div>
      </div>
        <div>
          <div class="k">Against Sales Invoice</div>
          <div class="v">{{ doc.get("against_sales_invoice") or doc.get("against_sales_order") or "—" }}</div>
        </div>
    </div>
  </div>

  <div class="buyer-box">
    <div class="section-title">Buyer Details</div>
    <div class="buyer-grid">
      <div>
        <div class="label">Customer Name</div>
        <div class="value">{{ doc.get("customer_name") or doc.customer_name or doc.get("customer") or "" }}</div>
      </div>
      <div>
        <div class="label">Address</div>
        <div class="value">{{ doc.shipping_address or doc.address_display or "" }}</div>
      </div>
    </div>
  </div>

  <table class="items-table">
    <thead>
      <tr>
        <th class="no">No.</th>
        <th class="code">Code</th>
        <th class="description">Description</th>
        <th class="qty">Qty</th>
        <th class="unit">Unit</th>
        <th class="price">Unit Price</th>
        <th class="amount">Amount</th>
      </tr>
    </thead>
    <tbody>
      {% for item in doc.items %}
      <tr>
        <td class="center">{{ loop.index }}</td>
        <td class="center">{{ item.item_code or "" }}</td>
        <td class="item-description">{{ item.item_name or "" }}</td>
        <td class="num">{{ frappe.format(item.qty, {"fieldtype":"Float"}) }}</td>
        <td class="center">{{ item.uom or item.stock_uom or "" }}</td>
        <td class="num">{{ frappe.utils.fmt_money(item.rate, currency=doc.currency) }}</td>
        <td class="num">{{ frappe.utils.fmt_money(item.amount, currency=doc.currency) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="bottom-grid">
    <div class="terms-area">
      {% if doc.get("tc_name") and doc.get("terms") %}
      <div class="terms-title">Terms &amp; Conditions</div>
      <div>{{ doc.terms }}</div>
      {% endif %}
      <div class="words"><b>Amount in Words:</b> {{ words }}</div>
    </div>
    <div>
      <div class="total-row"><span>Net Total</span><b>{{ frappe.utils.fmt_money(doc.net_total, currency=doc.currency) }}</b></div>
      <div class="total-row"><span>Tax</span><b>{{ frappe.utils.fmt_money(doc.total_taxes_and_charges or 0, currency=doc.currency) }}</b></div>
      <div class="grand-row"><span>Grand Total</span><b>{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</b></div>
    </div>
  </div>

  <div class="signature-row">
    <div>
      <div class="signature-line"></div>
      Received By
    </div>
    <div>
      <div class="signature-line"></div>
      Prepared By
    </div>
  </div>

  <div class="page-footer">
    <span>{{ company.company_name }}</span>
    <span>Page {{ page_number or 1 }} / {{ total_pages or 1 }}</span>
  </div>

</div>
"""

_DEMO_DELIVERY_NOTE_AR_HTML = r"""
{# ERPNext / Frappe Print Format: Delivery Note (AR) — company-agnostic, works on any site #}
{% set company = frappe.get_doc("Company", doc.company) %}
{% set words = frappe.utils.money_in_words(doc.grand_total or 0, doc.currency or company.default_currency) %}

<div class="invoice-page" dir="rtl">

  <div class="company-header">
    <div>
      {% if company.company_logo %}<img class="company-logo" src="{{ company.company_logo }}">{% endif %}
      <div class="company-name">{{ company.company_name or doc.company }}</div>
    </div>
    <div class="company-meta" style="text-align:left">
      {% if company.phone_no %}{{ company.phone_no }}<br>{% endif %}
      {% if company.email %}{{ company.email }}{% endif %}
    </div>
  </div>

  <div class="invoice-meta-bar">
    <div class="doc-title">إشعار تسليم</div>
    <div class="meta-grid">
      <div>
        <div class="k">رقم الإشعار</div>
        <div class="v">{{ doc.name }}</div>
      </div>
      <div>
        <div class="k">تاريخ التسليم</div>
        <div class="v">{{ frappe.format_date(doc.get("transaction_date") or doc.get("posting_date")) }}</div>
      </div>
        <div>
          <div class="k">رقم الفاتورة المرجعي</div>
          <div class="v">{{ doc.get("against_sales_invoice") or doc.get("against_sales_order") or "—" }}</div>
        </div>
    </div>
  </div>

  <div class="buyer-box">
    <div class="section-title">بيانات العميل</div>
    <div class="buyer-grid">
      <div>
        <div class="label">اسم العميل</div>
        <div class="value">{{ doc.get("customer_name") or doc.customer_name or doc.get("customer") or "" }}</div>
      </div>
      <div>
        <div class="label">العنوان</div>
        <div class="value">{{ doc.shipping_address or doc.address_display or "" }}</div>
      </div>
    </div>
  </div>

  <table class="items-table">
    <thead>
      <tr>
        <th class="no">م</th>
        <th class="code">الرمز</th>
        <th class="description">الوصف</th>
        <th class="qty">الكمية</th>
        <th class="unit">الوحدة</th>
        <th class="price">السعر</th>
        <th class="amount">المبلغ</th>
      </tr>
    </thead>
    <tbody>
      {% for item in doc.items %}
      <tr>
        <td class="center">{{ loop.index }}</td>
        <td class="center">{{ item.item_code or "" }}</td>
        <td class="item-description">{{ item.item_name or "" }}</td>
        <td class="num">{{ frappe.format(item.qty, {"fieldtype":"Float"}) }}</td>
        <td class="center">{{ item.uom or item.stock_uom or "" }}</td>
        <td class="num">{{ frappe.utils.fmt_money(item.rate, currency=doc.currency) }}</td>
        <td class="num">{{ frappe.utils.fmt_money(item.amount, currency=doc.currency) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="bottom-grid">
    <div class="terms-area">
      {% if doc.get("tc_name") and doc.get("terms") %}
      <div class="terms-title">الشروط والأحكام</div>
      <div>{{ doc.terms }}</div>
      {% endif %}
      <div class="words"><b>المبلغ بالحروف:</b> {{ words }}</div>
    </div>
    <div>
      <div class="total-row"><span>الإجمالي</span><b>{{ frappe.utils.fmt_money(doc.net_total, currency=doc.currency) }}</b></div>
      <div class="total-row"><span>الضريبة</span><b>{{ frappe.utils.fmt_money(doc.total_taxes_and_charges or 0, currency=doc.currency) }}</b></div>
      <div class="grand-row"><span>الإجمالي النهائي</span><b>{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</b></div>
    </div>
  </div>

  <div class="signature-row">
    <div>
      <div class="signature-line"></div>
      المستلم
    </div>
    <div>
      <div class="signature-line"></div>
      أعده
    </div>
  </div>

  <div class="page-footer">
    <span>{{ company.company_name }}</span>
    <span>صفحة {{ page_number or 1 }} / {{ total_pages or 1 }}</span>
  </div>

</div>
"""


KASIB_ASIA_TAX_INVOICE_NAME = "Kasib Asia Tax Invoice"

_KASIB_ASIA_PAYMENT_BADGE_MARKER = "payment-type-badge"

# Payment Type "Bank" (patches/v0_2_7). Sites that already have the badge
# get just this branch, inserted before the Credit one at that line's own
# indentation (kasibasia reformatted and restyled the badge in Desk, so the
# Credit line is matched by pattern, not by the exact text injected here);
# the badge CSS is left as the site has it.
_KASIB_ASIA_BANK_BADGE_MARKER = 'doc.custom_payment_type == "Bank"'
_KASIB_ASIA_BANK_BADGE_HTML = (
    '\n  {% elif doc.custom_payment_type == "Bank" %}'
    '\n  <div class="payment-type-badge bank">Payment Type: BANK</div>'
)
_KASIB_ASIA_CREDIT_BADGE_RE = re.compile(
    r'^([ \t]*)\{%-?\s*elif\s+doc\.custom_payment_type\s*==\s*["\']Credit["\']\s*-?%\}', re.MULTILINE
)

# Inserted right after the per-page copy-label div (Original/Duplicate/
# Triplicate Copy) so it repeats on every physical page, same as that
# label does.
_KASIB_ASIA_PAYMENT_BADGE_HTML = (
    '\n  {% if doc.custom_payment_type == "Cash" %}'
    '\n  <div class="payment-type-badge cash">Payment Type: CASH</div>'
    + _KASIB_ASIA_BANK_BADGE_HTML
    + '\n  {% elif doc.custom_payment_type == "Credit" %}'
    '\n  <div class="payment-type-badge credit">Payment Type: CREDIT</div>'
    '\n  {% endif %}'
)

# Positioned in the header's top-left margin (left 3%, top 0.6%-3.4%),
# mirroring .copy-label's own font-size/line-height -- confirmed empty by
# rendering a real submitted invoice through this format and visually
# inspecting the PDF; the rest of the page is a precisely positioned
# overlay onto a pre-printed background photo with no other free space.
_KASIB_ASIA_PAYMENT_BADGE_CSS = """
/* ---------- Payment Type badge (patches/v0_2_2) ---------- */
.payment-type-badge {
  position: absolute;
  left: 3%; top: 0.6%; width: 40%; height: 2.8%;
  z-index: 10;
  font-size: 11pt;
  font-weight: bold;
  text-align: left;
  line-height: 2.4mm;
}
.payment-type-badge.cash { color: #15803d; }
.payment-type-badge.bank { color: #1d4ed8; }
.payment-type-badge.credit { color: #b45309; }
"""


def _ensure_kasib_asia_payment_badge() -> None:
    """Add the Payment Type badge to "Kasib Asia Tax Invoice".

    That format is a fixed-position overlay onto a pre-printed background
    photo, built directly in Desk on kasibasia -- it is not otherwise
    managed by zatgo_core (module stays "Accounts", not "ZatGo Core") and
    is deliberately NOT captured here as a full literal template like the
    other formats in this file: doing a full-literal `_upsert_print_format`
    call would also reset its module/standard metadata, which is not part
    of what was asked. Instead this only inserts the badge markup
    (idempotent -- checks the marker class first) and appends the two
    badge CSS rules to the existing `css` field, leaving everything else
    on the doc untouched. No-ops on any site that doesn't have this print
    format (e.g. democompanysa).
    """
    if not frappe.db.exists("Print Format", KASIB_ASIA_TAX_INVOICE_NAME):
        return
    doc = frappe.get_doc("Print Format", KASIB_ASIA_TAX_INVOICE_NAME)
    if _KASIB_ASIA_PAYMENT_BADGE_MARKER in (doc.html or ""):
        credit = list(_KASIB_ASIA_CREDIT_BADGE_RE.finditer(doc.html))
        if _KASIB_ASIA_BANK_BADGE_MARKER not in doc.html and len(credit) == 1:
            indent = credit[0].group(1)
            bank = (
                f'{indent}{{% elif doc.custom_payment_type == "Bank" %}}\n'
                f'{indent}  <div class="payment-type-badge bank">Payment Type: BANK</div>\n'
            )
            at = credit[0].start()
            doc.html = doc.html[:at] + bank + doc.html[at:]
            doc.save(ignore_permissions=True)
        return  # already applied

    anchor = '<div class="copy-label">{{ COPY_LABELS[copy_index] }}</div>'
    if anchor not in (doc.html or ""):
        logger.warning(
            "%s: expected anchor not found, skipping payment-type badge "
            "injection (template may have changed since this was written)",
            KASIB_ASIA_TAX_INVOICE_NAME,
        )
        return

    doc.html = doc.html.replace(anchor, anchor + _KASIB_ASIA_PAYMENT_BADGE_HTML)
    doc.css = (doc.css or "").rstrip("\n") + "\n" + _KASIB_ASIA_PAYMENT_BADGE_CSS
    doc.save(ignore_permissions=True)


_KASIB_ASIA_PREV_BALANCE_MARKER = "prev-balance"

# The pre-printed background has a "Previous Balance" label with a real
# bordered input box next to it (confirmed by rendering a real invoice and
# measuring the box: x 392-573px, y 1467-1497px on a 1240x1755 A4-at-150dpi
# render -> left/top/width/height below). "Paid By", on the same row, has
# no box at all -- under 3px of blank space before "Previous Balance"'s own
# label starts -- so that one is deliberately left alone, same call as the
# pre-existing "Received By" signature field.
_KASIB_ASIA_PREV_BALANCE_HTML = (
    '\n  <div class="prev-balance">'
    '{{ frappe.utils.fmt_money(doc.get("vansale_previous_balance") or 0, currency=currency) }}'
    "</div>"
)

_KASIB_ASIA_PREV_BALANCE_CSS = """
/* ---------- Previous Balance (patches/v0_2_2) ---------- */
.prev-balance {
  position: absolute;
  left: 32%; top: 83.6%; width: 14%; height: 1.7%;
  z-index: 10;
  font-size: 7.5pt;
  font-weight: bold;
  color: #0d2a5e;
  text-align: center;
  line-height: 4.8mm;
  direction: ltr;
}
"""


def _ensure_kasib_asia_previous_balance() -> None:
    """Fill the (previously blank) "Previous Balance" box on "Kasib Asia
    Tax Invoice" using `vansale_previous_balance` -- already computed for
    every Sales Invoice on every zatgo_core site by
    `events/print_fields.py::populate_print_fields` (validate hook), so
    this is a template-only change; no new server-side computation.

    Same idempotent, targeted-insertion approach as the payment-type badge
    above (see its docstring) -- only touches html/css, module/standard
    metadata untouched, no-ops on any site without this print format.
    """
    if not frappe.db.exists("Print Format", KASIB_ASIA_TAX_INVOICE_NAME):
        return
    doc = frappe.get_doc("Print Format", KASIB_ASIA_TAX_INVOICE_NAME)
    if _KASIB_ASIA_PREV_BALANCE_MARKER in (doc.html or ""):
        return  # already applied

    anchor = '<div class="dynamic-field remarks wrap" dir="auto">{{ doc.remarks or doc.terms or "" }}</div>'
    if anchor not in (doc.html or ""):
        logger.warning(
            "%s: expected anchor not found, skipping previous-balance "
            "injection (template may have changed since this was written)",
            KASIB_ASIA_TAX_INVOICE_NAME,
        )
        return

    doc.html = doc.html.replace(anchor, anchor + _KASIB_ASIA_PREV_BALANCE_HTML)
    doc.css = (doc.css or "").rstrip("\n") + "\n" + _KASIB_ASIA_PREV_BALANCE_CSS
    doc.save(ignore_permissions=True)


_KASIB_ASIA_SINGLE_COPY_MARKER = "get_copy_label"


def _ensure_kasib_asia_single_copy_print_tracking() -> None:
    """Original/Duplicate Copy now comes from real print history, not a
    hardcoded 3-copies-per-job loop.

    Before 2026-09-24 the template printed a FIXED ["Original Copy",
    "Duplicate Copy", "Duplicate Copy"] triplicate in a single job, every
    time -- unrelated to whether the invoice had ever actually been
    printed before, and guaranteeing at least 3 physical pages per print
    (directly conflicting with a later "always exactly one page" ask).
    Replaced with a single copy per print action, labeled by
    zatgo_core.services.print_tracking.get_copy_label(doc), which reads
    (and, only on a genuine Print action via Frappe's own `trigger_print`
    signal -- never a preview -- atomically increments) the new
    Sales Invoice.custom_print_count field. See print_tracking.py's module
    docstring for why `trigger_print` is the closest reliable signal a web
    app has for "a real print happened" (no web app can observe ink
    actually leaving a printer), and add_print_count_field.py for the
    field. Text color also switched #0d2a5e -> #000000 throughout (dot-
    matrix ribbons are monochrome; "no unnecessary colors" was an
    explicit requirement).

    Same idempotent-guard shape as the two functions above, but this is a
    structural rewrite (remove the outer copy loop; recolor), not a
    simple anchor-based insertion -- not safely auto-re-appliable the
    same way, so this only detects and warns if the live doc has drifted
    back to the old behavior, rather than silently overwriting a
    possibly-since-edited template. Re-apply by hand (see zatgo-core git
    history around 2026-09-24) if this ever fires.
    """
    if not frappe.db.exists("Print Format", KASIB_ASIA_TAX_INVOICE_NAME):
        return
    doc_html = frappe.db.get_value("Print Format", KASIB_ASIA_TAX_INVOICE_NAME, "html") or ""
    if _KASIB_ASIA_SINGLE_COPY_MARKER in doc_html:
        return  # already applied
    logger.warning(
        "%s: no longer calls get_copy_label() -- looks reverted to the old "
        "hardcoded 3-copies-per-job loop. Re-apply the 2026-09-24 single-"
        "copy print-tracking change by hand.",
        KASIB_ASIA_TAX_INVOICE_NAME,
    )


def _ensure_sales_zg1_chrome_pdf_generator() -> None:
    """Force Sales ZG1's pdf_generator to "chrome", bypassing whatever a
    site's Print Format.pdf_generator Select options are otherwise
    restricted to.

    Some sites lock every Print Format on the site to "wkhtmltopdf" only
    (confirmed on democompanysa 2026-09-22, via a Property Setter --
    Property Setters can't be scoped to one document, so this restriction
    applies to every Print Format on that site, not just this one).
    Frappe's Select validation checks the *current* value against the
    *current* options on every save, even when the value isn't changing,
    so a plain `doc.pdf_generator = "chrome"; doc.save()` raises
    ValidationError there regardless -- confirmed directly, including on
    a document that already had "chrome" stored before the site-wide
    restriction existed.

    Sales ZG1's CSS Grid layout is confirmed broken under wkhtmltopdf (see
    the comment above its ensure_print_formats() call), so it must render
    via chrome specifically -- writing only the `pdf_generator` column
    directly is a deliberate, narrow bypass of Select validation for this
    one field on this one document, not a general escape hatch, and
    leaves the site's restriction intact for every other print format.
    """
    if not frappe.db.exists("Print Format", DEMO_TAX_INVOICE_NAME):
        return
    frappe.db.set_value(
        "Print Format",
        DEMO_TAX_INVOICE_NAME,
        "pdf_generator",
        "chrome",
        update_modified=False,
    )


def _upsert_print_format(
    name: str,
    *,
    html: str,
    doc_type: str = "Sales Invoice",
    css: str | None = None,
    margins: float | None = None,
    pdf_generator: str | None = None,
) -> None:
    if frappe.db.exists("Print Format", name):
        doc = frappe.get_doc("Print Format", name)
    else:
        doc = frappe.new_doc("Print Format")
        doc.name = name
        doc.doc_type = doc_type
        doc.module = "ZatGo Core"
        doc.standard = "No"
        doc.custom_format = 1
        doc.print_format_type = "Jinja"
        doc.disabled = 0
    doc.html = html
    doc.custom_format = 1
    doc.raw_printing = 0
    doc.disabled = 0
    doc.print_format_type = "Jinja"
    doc.doc_type = doc_type
    doc.standard = "No"
    doc.module = "ZatGo Core"
    if css is not None:
        doc.css = css
    if margins is not None:
        doc.margin_top = margins
        doc.margin_bottom = margins
        doc.margin_left = margins
        doc.margin_right = margins
    if pdf_generator is not None:
        doc.pdf_generator = pdf_generator
    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)


def ensure_print_formats() -> None:
    """Create or update all zatgo_core-managed print formats."""
    _upsert_print_format(PRINT_FORMAT_NAME, html=_HTML)
    _upsert_print_format(PRINT_FORMAT_80MM_NAME, html=_HTML_80MM, css=_CSS_80MM, margins=2)
    _upsert_print_format(QUOTATION_PRINT_FORMAT_NAME, html=_QUOTATION_HTML, doc_type="Quotation", margins=10)
    # wkhtmltopdf can't render this template's CSS Grid layout correctly --
    # re-confirmed directly 2026-09-22: live democompanysa had drifted to
    # "wkhtmltopdf" (contradicting the original note here) and every real
    # print was actually broken -- Buyer Details collapsed into stacked
    # unstyled boxes and the entire bottom half (totals, balance, bank
    # details, signatures) didn't render at all. A side-by-side render of
    # the same real invoice confirmed "chrome" produces the correct
    # layout. Must stay "chrome" -- pdf_generator is deliberately NOT
    # passed to _upsert_print_format here (that would go through
    # doc.save()'s Select validation, which some sites reject -- see
    # _ensure_sales_zg1_chrome_pdf_generator below for why and how it's
    # still forced).
    _upsert_print_format(
        DEMO_TAX_INVOICE_NAME,
        html=_DEMO_TAX_INVOICE_HTML,
        css=_DEMO_TAX_INVOICE_CSS,
        margins=15,
    )
    try:
        _ensure_sales_zg1_chrome_pdf_generator()
        # Commit now, not just at the end of this function -- a later
        # _upsert_print_format() call below can throw uncommitted (e.g.
        # the Quotation/Delivery Note formats hitting the same site-wide
        # pdf_generator restriction this function works around above, on
        # sites that also lock those), and an uncaught exception rolls
        # back the whole transaction, silently undoing this otherwise-
        # successful write along with it. Confirmed happening this way on
        # democompanysa 2026-09-22.
        frappe.db.commit()
    except Exception:
        logger.exception("Sales ZG1 chrome pdf_generator enforcement failed")
    _upsert_print_format(
        DEMO_QUOTATION_EN_NAME,
        html=_DEMO_QUOTATION_EN_HTML,
        doc_type="Quotation",
        css=_QUOTE_DN_CSS,
        margins=6,
        pdf_generator="chrome",
    )
    _upsert_print_format(
        DEMO_QUOTATION_AR_NAME,
        html=_DEMO_QUOTATION_AR_HTML,
        doc_type="Quotation",
        css=_QUOTE_DN_CSS,
        margins=6,
        pdf_generator="chrome",
    )
    _upsert_print_format(
        DEMO_DELIVERY_NOTE_EN_NAME,
        html=_DEMO_DELIVERY_NOTE_EN_HTML,
        doc_type="Delivery Note",
        css=_QUOTE_DN_CSS,
        margins=6,
        pdf_generator="chrome",
    )
    _upsert_print_format(
        DEMO_DELIVERY_NOTE_AR_NAME,
        html=_DEMO_DELIVERY_NOTE_AR_HTML,
        doc_type="Delivery Note",
        css=_QUOTE_DN_CSS,
        margins=6,
        pdf_generator="chrome",
    )
    try:
        _ensure_kasib_asia_payment_badge()
    except Exception:
        logger.exception("Kasib Asia Tax Invoice payment-type badge injection failed")
    try:
        _ensure_kasib_asia_previous_balance()
    except Exception:
        logger.exception("Kasib Asia Tax Invoice previous-balance injection failed")
    try:
        _ensure_kasib_asia_single_copy_print_tracking()
    except Exception:
        logger.exception("Kasib Asia Tax Invoice single-copy print-tracking check failed")
    frappe.db.commit()
