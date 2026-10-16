# Kasib Asia Tax Return Invoice — reference snapshot

Separate, DB-stored Print Format on `kasibasia.zatgoinnovation.com`
(`standard: "No"`, `module: "Accounts"`), always drawn on the return artwork. Not
a zatgo_core fixture; these two files are a plain reference copy of what is
live -- editing them does nothing on their own. Update the live doc directly
(`frappe.get_doc("Print Format", "Kasib Asia Tax Return Invoice")`, set
`.html`/`.css`, `.save()`). Sibling of `../kasib_asia_tax_invoice/`, which also
prints returns via its credit-note branch and is the Sales Invoice default; this
one is an older, simpler variant (black text, no payment badge).

## Update 2026-10-16: V5 artwork + positive amounts

Applied to the live doc; this snapshot is the exact HTML/CSS now stored there.

- **Background** `/files/KasibAsiaReturnV5.jpg` (same file the Tax Invoice format
  uses for returns; V4 stays on disk for rollback).
- **Same V5 customer-block changes as the Tax Invoice format**: name / VAT /
  address re-seated between the new printed labels, CR value and Arabic customer
  name now drawn (their labels are pre-printed on V5; this format had neither
  before), long English+Arabic name pairs step down in font and finally wrap
  (`fit-1/2/3`). Text stays black and the address row keeps this format's own
  position. The name font is 9pt (was 10pt) to share the row with the Arabic name.
- **Amounts print positive**: a return's negative quantities/amounts/totals are
  shown as absolute values (items, totals, amount in words, paid amount, previous
  balance), as the Tax Invoice format already did.
- **Verified** locally (`vansale1`, in-memory return + long-name cases + V4 control)
  and on kasibasia with the real return `SINV-00008` and invoice `S1-01` through a
  throwaway draft; the live render after the update was pixel-identical to the
  draft. `custom_print_count` unchanged by the renders.
- **Rollback**: re-save the previous HTML/CSS (the commit before this one).
- **Known, unchanged**: 5-integer-digit amounts lose their last digit in the
  "Total Excluding VAT" and Gross Total boxes (narrow field widths, same as before);
  a long invoice number (e.g. `ACC-SINV-RET-2026-00167`) is clipped in its box.
