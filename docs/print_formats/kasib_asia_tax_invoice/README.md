# Kasib Asia Tax Invoice — reference snapshot (2026-09-24)

This Print Format lives on `kasibasia.zatgoinnovation.com` only, as a DB-stored
custom doc (`standard: "No"`, `module: "Accounts"`) — it is **not** a
zatgo_core fixture and is not recreated by `ensure_print_formats()`. These two
files are a plain reference copy of what's live, kept here purely so future
changes have something to diff against; editing them does nothing on their
own — the live doc must be updated directly (`frappe.get_doc("Print Format",
"Kasib Asia Tax Invoice")`, set `.html`/`.css`, `.save()`).

`zatgo_core/setup/ensure_print_formats.py`'s
`_ensure_kasib_asia_single_copy_print_tracking()` only detects drift back to
the pre-2026-09-24 behavior and logs a warning — it does not re-apply this
snapshot automatically (see that function's docstring for why: this was a
structural rewrite, not a safe anchor-based string insertion like the
payment-badge/previous-balance patches next to it).

## What changed 2026-09-24

- **Copy label is no longer a hardcoded 3-copies-per-job loop.** The old
  template printed `["Original Copy", "Duplicate Copy", "Duplicate Copy"]` in
  a single print job, every time, regardless of whether the invoice had ever
  actually been printed before — guaranteeing at least 3 physical pages per
  print action. Replaced with one page per print action; the label comes from
  `zatgo_core.services.print_tracking.get_copy_label(doc)`, which reads (and,
  only on a genuine Print action, never a preview — see that module's
  docstring on why Frappe's `trigger_print` signal is the mechanism — atomically
  increments) the new `Sales Invoice.custom_print_count` field
  (`zatgo_core/patches/v0_2_2/add_print_count_field.py`).
- **Text color switched `#0d2a5e` → `#000000`** throughout (dot-matrix ribbons
  are monochrome; "no unnecessary colors" was an explicit requirement),
  including the two payment-type badge colors.
- **Long item names/Arabic names**: added `overflow-wrap: anywhere` and
  `word-break: break-word` to `.item-cell.desc` so a long name wraps within
  its fixed row height instead of overflowing — `overflow: hidden` on the
  same rule still caps it, so this only improves *how* it truncates, not
  whether it can push into the next printed row.
- **What did NOT change**: the item table is still a 10-fixed-row absolute-
  position overlay on `KasibAsiaFinal.jpg` (a pre-printed dot-matrix form —
  the row positions are pixel-calibrated to that artwork, see the `ROW_TOPS`/
  `ROW_HEIGHTS` comments in the HTML). An invoice with more than 10 items
  still spans a second page — that's a physical constraint of the pre-printed
  form, not something CSS/font-size changes can fit onto one page, and is
  unchanged from before this pass. QR code logic, VAT calculation fallback
  chain, Arabic customer/item fields, and all positioning math are untouched.

## Update 2026-09-24 (same day): customer address/mobile fallback

Real production data check: **no submitted Sales Invoice on kasibasia has
`customer_address` set**, and the one test invoice created programmatically
that did get it auto-populated (ERPNext's own controller fills it from the
customer's default address on insert) still had a blank `contact_mobile`
for a customer whose `Customer.mobile_no` *and* linked Contact's
`mobile_no`/`phone` are all genuinely blank too. Neither box was a template
bug -- the fields were already there, they just had nothing to read when the
invoice-level fields were empty.

Added a fallback chain instead of assuming invoice-level fields are always
populated: address now falls back to the customer's default Address
(`zatgo_core.services.print_helpers.get_party_default_address` -- a thin
Jinja-exposed wrapper around `frappe.contacts.doctype.address.address
.get_default_address`, needed because that module isn't reachable as a bare
`frappe.contacts...` dotted path from Jinja unless something else already
imported it first in that request -- confirmed by testing, not assumed);
mobile falls back to `Customer.mobile_no`. Verified against a real customer
that does have a default address (Trade Core International) -- address
fallback renders correctly. Mobile still renders blank for the customers
checked, correctly: there is no phone number anywhere in the system for
them (Customer, Contact, and invoice all blank) -- that needs someone to
actually enter the data, not a code fix.

## Update 2026-09-24 (same day, third pass): item Arabic name + address position

Two more fields the user pointed at turned out to be the same shape of bug
as the address/mobile fallback above -- a field the template already
referenced that either didn't exist or didn't have the data flowing into
it, discovered by actually rendering a real invoice to PDF and looking at
it (not just checking the HTML source) once visual bugs started showing up.

- **Item Arabic name**: `item.custom_item_name_ar` referenced in the
  template **does not exist as a field anywhere on Sales Invoice Item**
  (confirmed: raw SQL lookup throws `Unknown column`). The real Arabic name
  lives on the **Item master** as `zatgo_item_name_ar` (confirmed real data,
  e.g. "LUNA MILK FULLFAT 400 GM" -> "حليب لونا كامت الدسم 400 غرم"). Now
  looked up per row via `frappe.db.get_value("Item", item.item_code,
  "zatgo_item_name_ar")` instead of a nonexistent invoice-item field.
- **Customer phone**: turned out to live on none of invoice/Customer/Contact
  (all checked, all blank) for the customers tested -- but the **Address**
  record's own "Phone" field had it all along (confirmed: "TRADE CORE
  INTERNATIONAL Co.-Billing" has phone `99555222` there). Added as a third
  fallback, chained off the same `customer_address_name` already resolved
  for the address box.
- **Address box position**: once real address text started rendering (never
  possible before, since `customer_address` was never populated on any real
  invoice -- see above), it visually overlapped the pre-printed "عنوان
  العميل" Arabic label. Measured precisely by cropping both the background
  artwork (`KasibAsiaFinal.jpg`) and an actual rendered test PDF at the same
  region and comparing pixel positions (not guessed) -- the value box
  started at almost exactly the same x-position the label ends at, zero
  buffer. `.customer-address` moved from `left: 41.88%; width: 15.63%` to
  `left: 44.5%; width: 13.5%`, verified with a second render to confirm the
  gap. Address value also now renders as two explicit lines (`address_line1`
  then `city`, each its own `<div>`) instead of one comma-joined string.
- Root cause for why none of this was ever visible before: `customer_address`
  is essentially never set on a real kasibasia invoice (confirmed against
  live data), so these boxes had always rendered empty in production --
  nobody had ever actually seen text in them until the fallback chain above
  started supplying it.

Verified by actually rendering a real invoice to PDF (`frappe.get_print(...,
as_pdf=True)`) and visually inspecting it (converted to PNG, cropped, and
read as an image) rather than only checking HTML output -- caught the
position overlap this way, which regex-matching the HTML source would have
missed entirely.

## Verified (2026-09-24, against real submitted test invoices on kasibasia, cleaned up after)

- 3-item invoice → 1 page; first `trigger_print` render → `ORIGINAL COPY`,
  `custom_print_count` 0→1; a preview render in between does **not** increment
  the count; second and third `trigger_print` renders → `DUPLICATE COPY`,
  count →2→3.
- 12-item invoice → 2 pages (10 + 2), no Jinja errors.
- Long English (140-char, ERPNext's own Item Name field limit) + long Arabic
  (`custom_item_name_ar`, 140-char) + mixed English/Arabic item name → renders
  without error, stays on 1 page (2 items).
