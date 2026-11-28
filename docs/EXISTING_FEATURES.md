# Existing features

*Phase 0, 2026-11-28, `main` at `d5bc17b`.*

Status: **Live** = on production sites, as last recorded (2026-11-06 to 11-16). **Main** = on `main`, not known to be deployed. **Dormant** = shipped but switched off until a site enables it. "Problems" lists known issues only; Phase 1 has the full audit.

## Platform
| Feature | Purpose | Where | DocTypes | Depends on | Status | Problems / opportunities |
|---|---|---|---|---|---|---|
| ZatGo Apps hub and switches | turn each ZatGo app on or off per site | `services/app_catalog.py`, `app_state.py`, `app_gate.py`, `app_authority.py`, page `zg_app_hub` | ZG System Settings, ZG Registered Application | — | Live | 13 switches plus Industries plus licence: three overlapping "is it on" sources (see `DEPENDENCY_MAP.md`) |
| Desk layout (ZatGo folder, per-app sidebars) | one entry point, one sidebar per app | `events/boot.py`, `services/app_sidebar.py`, `core_sidebar.py`, `app_desk.py` | Workspace, Workspace Sidebar, Desktop Icon | Frappe v16 Desk | Live | sidebars rebuilt on migrate and settings save; user-specific navigation only through permissions |
| ZatGo ERP workspace | accounting and stock home over ERPNext screens | `zatgo_erp.json`, `services/erp_workspace.py`, `erp_summary.py`, 8 Number Cards | role ZG Accounts & Inventory | ERPNext Accounts and Stock | Main (11-22/23) | the uncommitted working tree adds 200 lines to its JSON |
| Settings framework | per-app settings with tabs; company, branch and user scopes | `services/settings_service.py`, `ui_settings.py`, `config_loader_service.py` | ZG * Settings, ZG Config Profile/History | — | Live | ZG Security Settings has no runtime effect; company and branch settings are not company-scoped by user |
| Subscription gate | read-only mode for lapsed Space tenants | `services/subscription_gate.py`, `public/js/zg_subscription_banner.js` | — (site_config `zg_subscription`) | ZatGo Space | Live, off unless pushed | `"*"` hooks run on every document event and permission check |
| Editions and licensing | signed offline licences, editions, feature gate, limits, audit | `licensing/`, pages `zg_licence`, `zg_edition_builder` | ZG Module, ZG Feature, ZG Edition (+ Feature), ZG Licence (+ History), ZG Audit Log | registry `catalog/` | Main, local only (6 commits unpushed); dormant | no production signing key yet; rollout runbook ready |
| Plugin registry | catalog projection for clients | `plugins/discover.py`, `services/plugin_registry_service.py` | ZG Registered Application, ZG Setting Section, ZG Client Application, ZG Application Registry (legacy) | catalog | Live | several overlapping "app list" DocTypes (10-23 tech debt) |
| Feature flags | legacy per-feature toggles | `services/feature_flag_service.py` | ZG Feature Flag | — | Live | overlaps switches and licensing |
| Duplicate Prevention | block, warn or suggest on duplicate masters and invoices | `services/duplicate/`, `api/v1/duplicate/`, `search_link` override | ZG Duplicate Rule (+ Field, Role), ZG Duplicate Prevention Settings, ZG Duplicate Override Log | 17 ERPNext DocTypes | Live (on by default) | uncommitted `v0_5_1` same-name block; sync callers don't handle `DuplicateRecordError` |
| Industries | vertical DocTypes and APIs | `industries/` | ZG Enabled Industry; Gym (Plan, Membership, Attendance); Jewellery (Metal Rate); Restaurant (Order, Table, KDS); Textile; Supermarket | registry | Live (per site) | — |
| Audit trail | change history | `mixins/auditable.py`, `licensing/audit.py` | ZG Audit Log, ZG Config History | — | Live | only some settings DocTypes use the mixin; server and git differ on `ZG POS Settings` |
| Theme and login page | SaaS Desk look | `services/ui_apps.py`, `public/saas_theme/`, `templates/saas_theme/login.html` | ZG Theme Settings | — | Live (per site) | two theme branches pushed, not merged |
| Language switcher | EN/AR toggle | `api/v1/language.py`, `public/language_switcher/` | ZG Language Settings | — | Live (per site) | `ar.csv` has 38 lines only |
| Mobile form cards | child tables as cards on phones | `public/js/zg_mobile_forms.js`, `css/zg_mobile_forms.css` | — | Desk | Live (11-16) | — |

## Sales, accounting and stock (on ERPNext documents)
| Feature | Purpose | Where | ERPNext DocTypes | Status | Problems / opportunities |
|---|---|---|---|---|---|
| Accounting API | create/submit/cancel/return invoices, payments, journals for web and desktop accounting | `api/v1/accounting/`, `services/erpnext_writes.py` (2,026 lines), `erpnext_reads.py` | Sales/Purchase Invoice, Payment Entry, Journal Entry, Quotation, Customer, Supplier | Live | **no tax template applied on API invoices** (verified 11-06); `client_id` optional on money endpoints; payload not compared on replay |
| User-wise Sales Invoice naming | series per user and company | `events/sales_invoice_naming.py`, `services/sales_invoice_naming.py`, `return_naming.py` | ZG Sales Invoice Naming Settings | Live | — |
| Multi-payment allocation | several methods/accounts on one SI or PE | `services/payment_allocation.py`, `overrides/` | ZG Payment Allocation, ZG Mode of Payment Account | Live | class mixins cached with hooks (clear-cache after deploy) |
| Cash invoice auto-payment | Cash SI/PI posts its Payment Entry; cancel cascades | `services/invoice_cash_payment_service.py`, `events/*_payment.py` | Payment Entry | Live | Cash returns leave an open credit note (11-06) |
| Narration | one narration field on 14 DocTypes | `services/narration.py`, patch `v0_2_5` | custom fields | Live | — |
| Source-warehouse auto-fill | fill warehouse on stock documents | `events/default_source_warehouse.py`, JS | SO, SI, DN, PR | Live (setting) | — |
| Payment Entry account from chart | pick Bank ledger automatically | `services/payment_entry_accounts.py`, `public/js/payment_entry.js` | Payment Entry | Live (setting) | — |
| Print formats | VanSale 80mm invoice, A4/80mm per user, Quotation, Kasib Asia, report formats, copy label, ZATCA QR | `setup/ensure_print_formats.py`, `services/sales_invoice_print.py`, `print_tracking.py`, `overrides/print_entry.py` | Print Format | Live | migrate overwrites managed formats; any reader can bump the duplicate-copy counter |
| ZATCA Phase 1 QR | TLV QR on invoices | `services/zatca_qr.py` | Sales Invoice (`zatca_qr_base64`) | Live | timestamp zone and non-SAR currency unconfirmed against the spec; Phase 2 lives in a separate app |
| Reports | Business Summary, Payment Method Summary, MyBis | `zatgo_core/report/`, `services/report_templates.py` | — | Live | two native reports only; dashboards are Number Cards |

## Client products
| Feature | Purpose | Where | DocTypes | Status | Problems / opportunities |
|---|---|---|---|---|---|
| VanSaleX | van sales: orders → invoices, returns, collections, trips, stock, purchases, settings and per-user access | `api/v1/vansalex/`, `services/vansalex_*.py` | VanSaleX Settings (+ Access), ZG Van Sale Profile, ZG Trip | Live | replay acks the wrong state; per-line write-off cap; uncommitted settings work |
| ZatGo POS (retail, restaurant) | counter sales, offline sales, cash sessions, split payment, credit sales, pages | `api/v1/retail_pos/`, `resto_pos/`, `services/*pos*.py`, `pos_session_service.py`, `offline_sale.py` | ZG POS Settings, ZG Order (+ Item), ZG Table, ZG KDS Ticket; POS Opening/Closing Entry | Live (sessions on a release branch) | `offline=1` skips price controls for any cashier where offline is allowed |
| MyBis | read-only BI API | `api/v1/mybis/`, `services/mybis/` | ZG MyBis Settings | Live (switch off by default) | raw SQL ignores `if_owner` restrictions; 18 tests not isolated |
| Customer/item sync | offline-first sync for mobile | `api/v1/sync/`, `services/customer_sync_*`, `item_sync_*` | Customer, Item, Address, Contact | Live | savepoint after commit in the batch |
| Delivery and fleet | stops, couriers, tracking | `api/v1/delivery/`, `fleet/` | ZG Delivery Stop, ZG Delivery Boy, ZG Vehicle | Live | dispatcher role undecided; POD OTP not checked |
| Portals | customer and vendor order views | `api/v1/customer_portal/`, `vendor_portal/` | Sales/Purchase Order | Live | — |
| CRM, HR, service, warehouse helpers | thin APIs over ERPNext | `api/v1/crm/`, `hr/`, `service/`, `warehouse/` | Lead, Employee, ZG Service Ticket, Item Group | Live | few tests |

## Bundled modules
| Module | Purpose | Where | DocTypes | Status | Problems / opportunities |
|---|---|---|---|---|---|
| ZatGo AI (Chat AI) | assistant with ERPNext tools, local models by default | `chat_ai/` | 16 `AI *` + Chat AI Settings | Live where switched on | managers can read every conversation; uncommitted tool hints |
| ZatGo Tracker | projects, tasks, time, org chart | `tracker/`, 3 pages | Tracker Settings, Tracker Activity Session; ERPNext Project/Task/Timesheet | Live where switched on | `list_for_doc` fixed 11-06; `add_member` and org edits not scoped |
| ZatGo Space (tenant side) | trial/plan orders for the SaaS platform | `zatgo_space/` | Space Order (+ App), Space Plan, Space Settings, Space Job Log | Live on `zatgoportal` only | token compared with `!=` and accepted in the URL |
