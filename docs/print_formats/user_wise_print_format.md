# User-wise Sales Invoice print format (A4 / 80mm)

Configured per user + company in **Sales Invoice Naming Settings → Rules → Printing**:
`A4 Print Format`, `80mm Print Format`, `Default Paper`, `Restrict to these formats`.
All optional; users without a rule (and Administrator) are unaffected.

- **VanSaleX (app / web)**: the app's 80mm choice (`VanSale Tax Invoice 80mm`) is swapped server-side for the user's own
  80mm format (e.g. a site's "Sales Invoice Signx 80mm"); a blank request uses the Default Paper. No app rebuild.
  Paper access (`sales_invoice.print_a4` / `print_80mm`) is still enforced and recognises the user's 80mm format.
- **Desk**: Print opens with the user's default format (boot `sales_invoice_print`, `public/js/sales_invoice.js`).
- **Restrict**: the user may print Sales Invoices only with the formats filled in on their rule (a blank slot is not
  offered). Enforced server-side for the Desk print view / PDF download (`overrides/print_entry.py`) and the VanSaleX
  PDF API. Known gap: opening `/printview` directly with the "Standard" format is not intercepted.

Code: `services/sales_invoice_print.py`. Tests: `tests/integration/test_sales_invoice_print.py`.
Needs `bench clear-cache` then `bench migrate` (new columns on the rule table).
