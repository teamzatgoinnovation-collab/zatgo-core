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


PRINT_FORMAT_80MM_NAME = "VanSale Tax Invoice 80mm"

# @page CSS is the standard Frappe/wkhtmltopdf mechanism for a thermal page
# size — there's no dedicated Print Format doctype field for it.
_CSS_80MM = "@page { size: 80mm auto; margin: 2mm; }"

# Compact stacked layout (no wide item table) for a ~72mm printable width.
_HTML_80MM = r"""
<style>
  .vt80 { font-family: DejaVu Sans, Arial, sans-serif; font-size: 10px; color: #111; width: 100%; }
  .vt80 .c { text-align: center; }
  .vt80 .title { font-size: 13px; font-weight: 700; margin: 0 0 2px; }
  .vt80 .title-ar { font-size: 11px; font-weight: 700; direction: rtl; margin: 0 0 6px; }
  .vt80 hr { border: none; border-top: 1px dashed #333; margin: 4px 0; }
  .vt80 .row { display: flex; justify-content: space-between; }
  .vt80 .item { margin: 3px 0; }
  .vt80 .item .name { font-size: 9px; }
  .vt80 .item .sub { font-size: 9px; color: #333; display: flex; justify-content: space-between; }
  .vt80 .totals td { padding: 1px 0; font-size: 10px; }
  .vt80 .totals .v { text-align: right; }
  .vt80 .grand { font-size: 11px; font-weight: 700; }
  .vt80 .qr { text-align: center; margin-top: 6px; }
  .vt80 .qr img { width: 90px; height: 90px; }
  .vt80 .foot { text-align: center; font-size: 8px; margin-top: 4px; }
</style>
{%- set company = frappe.get_doc("Company", doc.company) -%}
{%- set settings = None -%}
{%- if frappe.db.exists("DocType", "ZG Company Settings") -%}
  {%- set sname = frappe.db.get_value("ZG Company Settings", {"company": doc.company}, "name") -%}
  {%- if sname -%}{%- set settings = frappe.get_doc("ZG Company Settings", sname) -%}{%- endif -%}
{%- endif -%}
{%- set vat_no = (settings.tax_id if settings and settings.tax_id else company.tax_id) or "" -%}
{%- set qr_uri = tlv_to_png_data_uri(doc.get("zatca_qr_base64")) if doc.get("zatca_qr_base64") else "" -%}

<div class="vt80">
  <div class="title c">{{ company.company_name }}</div>
  <div class="c" style="font-size:9px">VAT: {{ vat_no or "—" }}</div>
  <div class="title-ar c">{{ "فاتورة ضريبية مبسطة" if not doc.get("is_return") else "إشعار دائن" }}</div>
  <div class="c" style="font-size:9px;font-weight:700">
    {{ "CREDIT NOTE" if doc.get("is_return") else "SIMPLIFIED TAX INVOICE" }}
  </div>
  <hr/>
  <div style="font-size:9px">Invoice: {{ doc.name }}</div>
  <div style="font-size:9px">Date: {{ frappe.utils.formatdate(doc.posting_date, "dd-MM-yyyy") }}</div>
  <div style="font-size:9px">Customer: {{ doc.customer_name or doc.customer }}</div>
  {% if doc.get("return_against") %}<div style="font-size:9px">Against: {{ doc.return_against }}</div>{% endif %}
  <hr/>
  {% for item in doc.items %}
  <div class="item">
    <div class="name">{{ item.item_name or item.item_code }}</div>
    <div class="sub">
      <span>{{ "%.2f"|format(frappe.utils.flt(item.qty)) }} x {{ "%.2f"|format(frappe.utils.flt(item.rate)) }}</span>
      <span>{{ "%.2f"|format(frappe.utils.flt(item.amount)) }}</span>
    </div>
  </div>
  {% endfor %}
  <hr/>
  <table class="totals" style="width:100%">
    <tr><td>Total VAT</td><td class="v">{{ "%.2f"|format(frappe.utils.flt(doc.total_taxes_and_charges)) }}</td></tr>
    <tr class="grand"><td>GRAND TOTAL</td><td class="v">{{ "%.2f"|format(frappe.utils.flt(doc.grand_total)) }}</td></tr>
  </table>
  {% if qr_uri %}
  <div class="qr"><img src="{{ qr_uri }}" alt="QR"/></div>
  {% endif %}
  <div class="foot">ZATCA Compliant E-Invoice</div>
</div>
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


def _upsert_print_format(
    name: str,
    *,
    html: str,
    doc_type: str = "Sales Invoice",
    css: str | None = None,
    margins: float | None = None,
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
    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)


def ensure_print_formats() -> None:
    """Create or update all zatgo_core-managed print formats."""
    _upsert_print_format(PRINT_FORMAT_NAME, html=_HTML)
    _upsert_print_format(PRINT_FORMAT_80MM_NAME, html=_HTML_80MM, css=_CSS_80MM, margins=2)
    _upsert_print_format(QUOTATION_PRINT_FORMAT_NAME, html=_QUOTATION_HTML, doc_type="Quotation", margins=10)
    frappe.db.commit()
