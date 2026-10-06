# Narration on transactions

Every transaction document has a **Narration** section on its main tab,
right after the main table, visible on a new form before the first save.
It holds:

- **Narration:** optional, user-editable.
- **Attachment** (`custom_attachment`, Attach): a file can be added before
  the first save, when the form sidebar's Attachments panel isn't shown
  yet. Frappe links it to the document on save. More files go through the
  sidebar after saving. Editable after submit too.

| Doctype | Narration field | Section placed after |
|---|---|---|
| Payment Entry | `remarks` (native) | Transaction ID (reference no. / date) |
| Journal Entry | `remark` (native) | Accounting Entries table |
| Sales / Purchase / POS Invoice, Stock Entry, Purchase Receipt | `remarks` (native) | Items table |
| Sales Order, Purchase Order, Quotation, Delivery Note, Material Request, Stock Reconciliation | `custom_narration` | Items table |

Native fields are relabelled "Narration" and moved into the section; they
already flow into GL Entry `remarks`, so ledger reports show the narration.
The section and its fields are placed with a `field_order` property setter
(what Customize Form saves), recomputed from the site's current layout so
other customisations are kept. Code: `patches/v0_2_5/add_narration_fields.py`,
also run on every migrate via `setup/ensure_custom_fields.py`.

**Payment Entry / Journal Entry:** ERPNext rewrites `remarks` / `remark`
with auto-text on every save unless its own "Custom Remark(s)" flag is set.
The flag is set for the user:
- `services/narration.py` (`before_validate`): an edited narration on a
  saved document sets the flag; clearing it unsets the flag, so the auto-text
  returns.
- `public/js/payment_entry.js`, `journal_entry.js`: the same when typing,
  including on a new, unsaved document.
- A narration left alone keeps following ERPNext's auto-text.
- ERPNext's own internally created JEs are unaffected.

API: `accounting.payments.create_receive` / `create_pay` /
`create_*_advance` / `update` take `remarks`; `accounting.quotations.create`
/ `update` take `narration`. SI/PI already take `remarks`, JE takes
`user_remark`. Read endpoints return `narration` for PE, JE, SI, PI and
Quotation.

Tests: `tests/integration/test_narration.py`.
