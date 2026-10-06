# Narration on transactions

Every transaction document has a visible, user-editable **Narration**
(optional). Attachments need nothing extra: the form sidebar's Attach works on
all of them (and `upload_file` for API clients).

| Doctype | Narration field | Where |
|---|---|---|
| Payment Entry | `remarks` (native) | More Information section (ERPNext shows it once accounts + amounts are filled) |
| Journal Entry | `remark` (native) | More Info tab |
| Sales Invoice, Purchase Invoice, POS Invoice | `remarks` (native) | More Info tab (SI: once a customer is set) |
| Stock Entry, Purchase Receipt | `remarks` (native) | Other Info / More Info tab |
| Sales Order, Purchase Order, Quotation, Delivery Note, Material Request | `custom_narration` | top of the More Info tab |
| Stock Reconciliation | `custom_narration` | end of the form |

Native fields are relabelled "Narration" and their section is shown
expanded. They already flow into GL Entry `remarks`, so ledger reports show
the narration. Code: `patches/v0_2_5/add_narration_fields.py` (+
`setup/ensure_custom_fields.py`).

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
