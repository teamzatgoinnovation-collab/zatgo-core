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

## Verified (2026-09-24, against real submitted test invoices on kasibasia, cleaned up after)

- 3-item invoice → 1 page; first `trigger_print` render → `ORIGINAL COPY`,
  `custom_print_count` 0→1; a preview render in between does **not** increment
  the count; second and third `trigger_print` renders → `DUPLICATE COPY`,
  count →2→3.
- 12-item invoice → 2 pages (10 + 2), no Jinja errors.
- Long English (140-char, ERPNext's own Item Name field limit) + long Arabic
  (`custom_item_name_ar`, 140-char) + mixed English/Arabic item name → renders
  without error, stays on 1 page (2 items).
