# Current architecture

*Phase 0, 2026-11-28, `main` at `d5bc17b`. What the code does today, not what it should do (`TARGET_ARCHITECTURE.md`).*

## 1. Shape
```
Clients: Desk (browser) · VanSaleX (Flutter, + /vansalex web) · ZatGo POS (Electron) · MyBis (Flutter) · web/desktop accounting
        │  /api/method/zatgo_core.api.v1.<domain>.<fn>   (488 whitelisted methods, envelope {success,data,meta,error})
        ▼
before_request:  subscription_gate.gate_requests → app_gate.gate_api → industries.gate.gate_industry_api → ui_apps.add_desk_includes
        ▼
api/v1/<domain>/*.py   thin handlers (mostly)  ──►  services/*.py  business rules  ──►  ERPNext document controllers
                                                       │                               (insert/submit/cancel; GL + stock ledger)
                                                       └─► permissions/, row_scope, idempotency, vansalex_access, licensing.gate
doc_events on ERPNext DocTypes (events/, services/)  ·  "*" hooks: subscription gate, licence gate, Chat AI indexing
```
ERPNext owns the General Ledger and the Stock Ledger. zatgo_core never writes them; raw SQL against them is read-only (`services/mybis`, reports).

## 2. How it hooks into Frappe and ERPNext (`hooks.py`)
| Mechanism | Used for |
|---|---|
| `required_apps = ["erpnext"]`, `before_install` | refuses a major other than 16; creates Activity Type "Execution" |
| `after_install` / `after_migrate` | roles, singletons, number series, feature flags, then the shared idempotent steps (`install._SHARED_STEPS`: custom fields, Mode of Payment, print formats, VanSale perms, ERP perms, core Desk, bundled modules, industries, licensing sync, plugin registry); each step is isolated and logged |
| `before_uninstall` | removes legacy Desk records only; data stays |
| `boot_session` | `frappe.boot.zatgo_core`: app switches, routes, ZatGo folder, subscription and licence state |
| `before_request` (4) | subscription read-only gate, app API gate (404), industry API gate, per-request Desk JS/CSS |
| `page_renderer` | themed login page when the theme is on |
| `doctype_js` (9 DocTypes), `page_js` (stock-balance) | form behaviour: payment pickers, source warehouse, narration, naming links |
| `jinja.methods` (4) | ZATCA QR, copy label, party address for print formats |
| `doc_events` | 15 ERPNext DocTypes plus `"*"`; Duplicate Prevention appends its `validate` to 17 DocTypes in a loop at import time |
| `extend_doctype_class` | Sales Invoice (offline stock), Payment Entry (split bank GL line) |
| `override_whitelisted_methods` | old method paths (`compat_methods`), print view and PDF (user-wise print format), query report run/export, `search_link` (duplicate-aware search) |
| `permission_query_conditions` / `has_permission` | owner scope (device tokens, preferences), company scope, Tracker, Chat AI per-user; `"*"`: subscription gate, licence gate, bundled-module gate, industry gate |
| `scheduler_events` | `all`/`hourly`/`daily` Chat AI wrappers, MyBis daily report, `services.jobs.daily` |
| `fixtures` | Role only (8 ZatGo roles) |

## 3. How it extends ERPNext data
- **Custom fields** come from code (`setup/ensure_custom_fields.py`, which calls the patch functions under `patches/`) on every migrate, not from fixtures. That is a deliberate self-heal after patches were found "recorded as run" without the columns. Touched: Sales Invoice (8 groups), Purchase Invoice, Payment Entry, Warehouse, Supplier, Customer, Item, Company, Stock Entry, Sales/Purchase Order, Quotation (+ Item), Journal Entry, Mode of Payment, Address, Contact.
- **Idempotency**: `zatgo_client_id` (unique index) on every client-created document; `services/idempotency.insert_idempotent` recovers the duplicate-key race.
- **Property setters** in code: narration labels, multi-payment fields, licensing.
- **Custom DocPerm** rows: VanSale roles (`setup/ensure_vansale_perms.py`, now copying standard rows first), ERP perms, Tracker roles, licensing.
- **Print formats** created or refreshed by `setup/ensure_print_formats.py` (2,500 lines) and the report formats. Migrate overwrites managed formats.
- **No ERPNext core file is modified.**

## 4. Settings
- **ZG System Settings** (Single) holds the app switches (`enable_*`, 13), Industries, and system options. Writing a switch is System Manager only, enforced in the controller (`services/app_authority.py`).
- **One settings DocType per app**, each starting with a Tab Break: VanSaleX Settings, ZG POS Settings, ZG MyBis Settings, ZG Theme/Language Settings, ZG Duplicate Prevention Settings, Chat AI Settings, Tracker Settings, Space Settings. Each Tab Break becomes a sidebar item.
- **Scoped settings**: ZG Company Settings (per company), ZG Branch Settings, ZG Van Sale Profile (per user), ZG Sales Invoice Naming Settings (user + company), user-wise print formats.
- **Platform settings** (Singles): ZG Application, Integration, Notification, Number Series, Payment, Printer, Security, Storage, Sync Settings. **ZG Security Settings is not read by any code** (10-23 M6, unchanged).
- **site_config** carries what a site admin must not change: `zg_subscription` (pushed by Space), `zg_licence_enforcement`, `zg_licence_issuer`, `zg_site_id`, `space_internal_token`.
- Readers: `services/app_state.py` is the only reader of the switches. `vansalex_settings.resolve*` resolves VanSaleX. `pos_settings` resolves POS. ERPNext's own settings (Selling, Buying, Stock, Accounts) are used as defaults first.

## 5. Navigation: workspaces and sidebars
- One catalog, `services/app_catalog.py` (core entries in `plugins/manifests/core_apps.py`, plus `<module>/app_manifest.py`), drives the switch fields, API gate, hub cards, sidebars and plugin registry.
- **Desk**: the Apps screen shows a **ZatGo** folder (`events/boot.py`) listing every app that is on and that the user may open, plus General Settings. Each app has its own Workspace Sidebar (`services/app_sidebar.py`) with Overview, then Settings (one item per Tab Break), then its cards. App off = sidebar synced to no items, workspace hidden. Rail icons always hidden.
- **ZatGo ERP** workspace (`zatgo_erp.json`, `services/erp_workspace.py`, `erp_summary.py`): accounting and stock links to ERPNext screens, Number Cards, a summary block that respects User Permissions, and the role "ZG Accounts & Inventory".
- Synced workspace files sit in `zatgo_core/workspace/`. Bundled modules keep theirs in `<module>/desk_records/` and create them in `bootstrap`. Old routes redirect through `public/js/zg_route_redirects.js`.

## 6. Users and permissions
- **Roles** (fixture + `setup/ensure_roles.py`): ZG Company Admin, ZG Branch Admin, ZG Application Admin, ZG Read Only, VanSale User, VanSale Admin, ZG Invoice Naming Manager, ZG Accounts & Inventory. Others: Chat AI Manager/User, Tracker roles, ZG Gym Manager/User, Delivery.
- **DocType permissions** in JSON (System Manager on 71 DocTypes, ZG Application Admin 29, ZG Read Only 22, ZG Company Admin 17). Staff-wide DocTypes grant `Desk User`, not `All`.
- **Row scope**: `services/row_scope.py` applies Company User Permissions in SQL where `get_list` cannot. Owner scope applies to device tokens and preferences. VanSaleX field users have warehouse and feature limits (`vansalex_access`, `vansalex_stock_rules`) with a DocType backstop on REST and Desk.
- **Gates layered on top**: app switch (API 404), industry, subscription read-only, licence (dormant). Visibility (sidebar, folder) and security (gates, permission hooks) are separate code paths.

## 7. Data storage
84 DocTypes (`DOCTYPE_CATALOG` comes in Phase 4). Singles hold settings. Transactional ZatGo data: ZG Trip, ZG Order (+ Item), ZG Table, ZG KDS Ticket, ZG Delivery Stop/Boy, ZG Vehicle, Gym, Jewellery and Metal Rate, AI conversation tables, Tracker activity, Space orders. Logs: ZG Audit Log (append-only), ZG Config History, ZG Duplicate Override Log, ZG Licence History, AI logs. Everything financial is an ERPNext document.

## 8. Upgrades
- `patches.txt`: 52 patches in `[pre_model_sync]` / `[post_model_sync]` sections. A patch that needs new columns must be post-model-sync.
- `after_migrate` re-runs every idempotent setup step. A missing column or Desk record heals on the next migrate.
- Default-on switches need a patch that stores `1` (a Check on a Single reads 0 when unset).
- DocType JSON edits need a bumped `modified`, or migrate skips them. A new module in `modules.txt` needs `clear-cache` before `migrate`.
- **Production deploys are delta tars** copied into five containers (`deploy-staging/`, `docs/deployment.md`). The server tree drifts from git (for example the Settings Map files and the `zg_pos_settings.py` mixin).
