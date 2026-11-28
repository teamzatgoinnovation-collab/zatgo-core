# Compatibility audit

*Phase 1, 2026-11-28, `main` at `d5bc17b`. Target: Frappe/ERPNext v16 (local 16.29/16.31, production image 16.34.1). Also: what breaks first on v17.*

## Findings
| ID | Sev | Customization | Why it can break on an ERPNext/Frappe upgrade | Recommendation | Prio |
|---|---|---|---|---|---|
| C-01 | HIGH | `override_whitelisted_methods` of core methods: `frappe.www.printview.get_html_and_style`, `frappe.utils.print_format.download_pdf`, `frappe.desk.query_report.run` / `export_query`, `frappe.desk.search.search_link` | The wrappers mirror Frappe's signatures. A new upstream parameter is silently dropped (this happened with `search_link` on 11-04 and was fixed with `_UPSTREAM_PARAMS` forwarding for `query_report`). | One forwarding helper that passes through unknown kwargs; a unit test per override that compares the wrapper's signature with the installed Frappe function. | P1 |
| C-02 | HIGH | Calls into ERPNext internals (`get_payment_entry` ×12, `make_return_doc` ×8, `get_taxes_and_charges`, `make_sales_invoice` mappers, `make_closing_entry_from_opening`, `get_party_account`, …) | Not a public API; minor releases rename or change them. | Keep them behind one adapter module (`services/erpnext_adapter.py`, Phase 3) so an upgrade is fixed in one place; an integration test per call. | P2 |
| C-03 | HIGH | DocType names without a prefix (ADR-005) | Generic names (`Order`, `Table`, `Trip`, `Module`, `Feature`, `Licence`, …) can collide with a DocType a future ERPNext, Frappe or another installed app adds; until the lines are joined, two schemas exist. | Name-collision check at install and migrate (refuse with a clear message), plus a unit test against the apps on our benches; join the branches onto the rename line. | P1 |
| C-04 | MED | `extend_doctype_class` on Sales Invoice and Payment Entry (hrms also extends Payment Entry) | Supported mechanism, but the mixins override `make_sl_entries` and `add_bank_gl_entries` with ERPNext's internal signatures. | Signature-check test against the installed ERPNext. | P2 |
| C-05 | MED | `doctype_js` wrapping ERPNext form internals (`public/js/payment_entry.js` wraps `erpnext.accounts.pos.get_payment_mode_account` and the paid_to/paid_from queries; `sales_invoice.js`, `purchase_invoice.js`) | Depends on ERPNext JS names and load order. | Keep the wrapper surface small; a browser smoke test of those forms per upgrade. | P2 |
| C-06 | MED | Desk v16 structures: Workspace Sidebar, Desktop Icon, `navigate_to_tab`, icon label == sidebar name | v16-specific; v17 may change them. | Keep all Desk record writing in `app_sidebar` / `app_desk` / `ensure_core_desk` (already so); upgrade test on a fresh bench. | P2 |
| C-07 | MED | Custom DocPerm on ERPNext DocTypes | Standard rows ignored once a custom row exists. New ERPNext permissions on those DocTypes are not picked up, because the copy is taken once. | On each ERPNext upgrade, diff standard vs custom rows and report new standard rows (`deploy_check`). | P2 |
| C-08 | LOW | Deprecated calls | `page_length` / `limit_page_length` (204 uses, V17 deprecation warnings in tests), `frappe.cache()` as a call (8). | Will break on v17. | Mechanical replacement (`limit=`, `frappe.cache`) in one change. | P3 |
| C-09 | LOW | Print formats managed by code; Kasib Asia customer-specific formats in the generic app | Upgrades to ERPNext print variables can break them; a customer's format ships to every site. | Move customer-specific formats to site-level or an optional pack. | P3 |
| C-10 | INFO | Custom fields via `create_custom_fields` (31 callers), not fixtures | Survive upgrades; ERPNext adding a field with the same name would clash (all ZatGo fields are prefixed `zatgo_`, `zg_`, `custom_`, `vansale_`). | Keep the prefix rule; test for clashes on upgrade. | — |

## Version matrix (today)
| zatgo_core | Frappe | ERPNext | Python | Verified |
|---|---|---|---|---|
| `main` (`d5bc17b`) | 16.x | 16.x | ≥ 3.11 | test suite on local 16.29/16.31 (11-06 baseline); production image 16.34.1 runs `1a0e621` |

Fresh install on a clean v16 site: the install pins and `before_install` check landed on 11-22 (`3ce7a95`). **No clean-site install has been recorded since.** That is part of Phase 14.
