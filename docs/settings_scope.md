# ZatGo settings scope audit — 2026-10-31

Where every ZatGo app is configured, at which **scope**, who may change it, whether the server **enforces** it, and what the
client apps (mobile, web, desktop) read or keep on the device. Static audit of `zatgo_core` at `2af9fb9` plus the client apps and
shared SDKs in this workspace; nothing was run except where a line says *verified*. File references are relative to
`zatgo_core/` (the Python package) unless they start with a repo folder.

The **Settings Map** (Desk page `zg-settings-map`) shows these same facts as live controls; its per-field notes
(`services/settings_notes.py`) are built from this document.

## 1. How to read it

**Scope** — who a value applies to:

| Scope | Meaning | Where it lives |
|---|---|---|
| Site | one value for the whole site | every Single DocType (`ZG ... Settings`), app switches, industries, feature flags |
| Company | per company | `ZG Company Settings` (named by company), Mode of Payment accounts, invoice naming rules (with user) |
| Branch | per branch | `ZG Branch Settings` (the client passes the branch; there is no user-to-branch resolver yet) |
| User | per user | `ZG User Preferences`, `ZG Van Sale Profile` (overrides VanSaleX Settings), naming rules, user default Company |
| Role | per role | VanSale `user_type`, Tracker Top / Sub / Worker |
| Device / client | per installed client | `ZG Client Application` rows (app key x platform), device tokens, **preferences kept on the device** |
| Warehouse | per warehouse | transfer-point flag |

**Status** — what the setting does today:

| Status | Meaning |
|---|---|
| **Enforced** | server code reads it and refuses or changes behaviour |
| **Read by client** | served through an API and used by a client app, not enforced by the server |
| **Informational** | stored (and maybe served), but no code acts on it |
| **Not wired yet** | exists in the backend, is served, and **no client reads it and no server code enforces it** |

Default-on Checks on a Single read `0` when nothing was ever stored: read `tabSingles` (`services/app_state.py:63`), not the
cached document.

## 2. Platform (core settings)

Editors: System Manager, ZG Application Admin, ZG Company Admin unless noted. `api/v1/settings.save_settings` covers 15 core
DocTypes and checks `assert_can_write_settings` (`permissions/guards.py:46`) before DocType permissions; category `system` is
System Manager only. The apps below (VanSaleX, POS, Theme, Language, MyBis, Chat AI, Tracker, Space) are **outside** that API.

| DocType | Scope | Fields (by control) | Status |
|---|---|---|---|
| ZG System Settings | Site | 28 shown: 17 switches, 6 links, 2 choose-one, 1 text, 1 number, 1 table (+4 hidden legacy: brand, logo, theme, language) | Enforced: the 9 app switches, industries, `enable_ifrs_reports`, `autofill_source_warehouse`, `autofill_payment_entry_account`, `stock_summary_live_only`. Boot-only: `autofill_payment_accounts`, `maintenance_mode`. Rest informational |
| ZG Company Settings | Company | 28 (11 links, 5 text, 4 switches, 2 rich text, 2 colours, 1 choose-one, ...) | Partly enforced: default warehouse (VanSaleX, both POS), cash account, tax template, `tax_id` (ZATCA). `enable_negative_stock` is copied to Stock Settings only on an API save |
| ZG Branch Settings | Branch | 16 (7 text, 3 links, 2 times, 2 switches) | Informational |
| ZG Payment / Printer / Sync / Number Series | Site | 13 / 14 / 7 / 1 table | Informational (no client reads them) |
| ZG Security | Site, System Manager only | 15 (8 switches, 5 numbers) | Informational: floors are checked, not wired to Frappe's own policy |
| ZG Integration, Storage | Site | 31 (16 switches, 10 secrets) / 19 | Informational |
| ZG Notification | Site | 12 | Partly: `push_enabled`, `fcm_server_key` (`api/v1/devices.py:100`) |
| ZG Feature Flag | Site (optional company / branch) | 9 | Informational: nothing gates on it, `rollout_percent` unused |
| ZG User Preferences | User, owner-scoped; API save System Manager only | 9 (`theme`, `sidebar_collapsed`, ...) | Informational: no client uses it |
| ZG Application Settings + Client Application rows | Site / client | 6 + 12 per row | Informational / advisory: `clients_require_auth`, `block_disabled_clients` are unread |
| ZG Sales Invoice Naming | User x company rules + site `unmapped_user_behavior` | 1 choose-one + rule rows | Enforced (can block invoice creation); editors: System Manager, Accounts Manager, ZG Invoice Naming Manager |

Read APIs for the core settings: `settings.get_system_settings` (System Manager), `get_company_settings`, `get_branch_settings`,
`get_user_preferences`, `features.get_feature_flags`, `apps.get_application_settings`, `integrations.get_printers`,
`config.get_settings`. The Desk boot (`events/boot.py`) sends `system{brand_name, theme, default_company, maintenance_mode,
autofill_payment_accounts, enable_ifrs_reports}`.

## 3. Apps

| App | Settings | Scope | Fields | Status |
|---|---|---|---|---|
| **ZatGo VanSaleX** | `VanSaleX Settings` (3 tabs) + per-user `ZG Van Sale Profile` | Site = one client; User overrides | 14 (7 switches, payment type, discount %, max write-off qty, access table of 30 keys: 16 modules + 14 features); profile 17 (8 Inherit/Yes/No selects, warehouse, cash account, off-only access overrides) | **Enforced** everywhere: `services/vansalex_access.py:202` (effective = client on AND profile not off AND parent on), `:241` require, `:443` DocType backstop. `allow_orders`, `max_discount_percent`, `max_adjust_qty` are not user-overridable. Served by `vansalex.me.context` (`api/v1/vansalex/me.py:22`) |
| **ZatGo POS** | `ZG POS Settings` (General / Payments / Receipt & Printing) | Site | 13: **POS Type** (6 choices), default warehouse / price list / customer, discounts (allow, max %), default payment mode, split payment, receipt header / footer, tax on receipt, copies | **Only `pos_type` has an effect** (engine, industry, vertical); everything else is served by `pos_settings.get` and **not wired yet**: no client calls it (*verified*: no caller in `desktop/zatgo-pos` or `packages/`), and server code enforces none of it (`services/resto_pos_service.py:711` caps a discount only at the subtotal; the warehouse and "Walk-in Customer" ignore the settings) |
| **ZatGo AI** | `Chat AI Settings` (6 tabs) | Site | 89: 36 switches, 22 numbers, 15 text, 8 choose-one, 3 secrets, 3 decimals, 2 long text | **Enforced** (`chat_ai/core/quota.py:25`, local-only guard); Super-set of limits, tools, voice, files, costs |
| **ZatGo Tracker** | `Tracker Settings` | Site; role flags per user | 2 links (`default_company`, `default_activity_type`) | Enforced |
| **ZatGo Space** | `Space Settings` | Site | 2 numbers (`ram_pool_mb`, `disk_pool_mb`) | Informational (soft pools) |
| **ZatGo MyBis** | `ZG MyBis Settings` | Site; user default Company wins | 2 (`default_company`, `default_preset`) | Read by client, but the app ignores `default_preset` (and `week_start`) today |
| **ZatGo Desk Theme** | `ZG Theme Settings` | Site | 3 (brand name, logo, theme) | Informational: read by the Desk boot and `settings.get_system_settings` through `services/ui_settings.py` |
| **ZatGo Language Switcher** | `ZG Language Settings` | Site | 1 (default language) | Informational; each user's language stays on Frappe's `User.language` |
| **ZatGo VanSaleX Web** | switch only | Site | none | Enforced (serves `/vansalex`); requires VanSaleX |
| **Industries** (Restaurant, Gym, Jewellery, Textile, Supermarket) | rows of `ZG System Settings` | Site | one switch each | Enforced: API 404, permission hooks, Desk entries. Supermarket = the retail POS engine |

## 4. Client apps: on the device versus in the backend

`desktop/...`, `mobile/...`, `web/...` roots; "T / S / X / N" = toggle / choose-one / text / number.

| Client | Settings the user changes on the device | Backend settings it reads | No backend home yet |
|---|---|---|---|
| **flutter-vansalex** | language S; printers (name X, paper S, copies N 1-5, default T); site URL X | `vansalex.me.context`: company, warehouse, accounts, payment type, credit / bank / orders switches, warehouse + payment-type display, route-only collections, max discount, tax, print format, and the access matrix | default printer / paper / copies (ZG Printer Settings is not read), language, currency (SAR hard-coded in 29 files), 2-decimal rounding, week start |
| **mybis** | theme S, date format S, decimals S, currency position S, default company S, default period S, auto-refresh S, alerts T + severity S, 9 KPI cards T, export format S, offline copy T, server X | `mybis.context.get_context` (companies, default company / preset, areas, presets, week start) | refresh interval and severity, hidden KPIs, export format, **offline copy (a security policy)**, display formats; insight thresholds are hard-coded server-side |
| **zatgo-pos** | tables / orders / KDS toggles T (can only narrow what the site allows), receipt printer S, auto-print T, silent print T, open drawer T, site URL X, theme | `pos_profile.get` only (mode, vertical, industries, company, currency, tax, payment modes) | everything in `pos_settings.get`; per-terminal modules; printer settings of ZG Printer Settings; payment methods are hard-coded cash / card / wallet; receipts hard-code `$`, title, 80 mm |
| **desktop-accounting** | theme | `ZG Company Settings.enable_negative_stock` (the one setting page) | tax, terms, accounts, currency; money shown with 2 decimals and no currency |
| **web-accounting** | theme | none (no settings page; a dead `allowMockWithoutLogin` flag in the session) | same as desktop-accounting |
| **zatgo-vansalex-native** | none (flutter-vansalex in a WebView) | — | the target site is fixed in `capacitor.config.json`; changing it needs a rebuild |

Hard-coded behaviour that should become backend settings: currency and precision (VanSaleX, POS, accounting clients), week
start (Monday), payment methods and print width in the POS, discount cap in the POS cart, tenant URLs (the `zatgo-hub` lookup
exists and is called by nothing).

## 5. Shared SDKs

The backend has **334** whitelisted methods under `api/v1`.

| SDK | Covers | Notes |
|---|---|---|
| `@zatgo/erpnext` (`packages/zatgo-packages/erpnext`) | **234** | live; nested `ZatGoCoreApi` 183, `TrackerApi` 47, flat `WhitelistMethods` 230; header claims 155 |
| `@zatgo/sdk` (`packages/zatgo-packages/ts-sdk`) | 139 | stale copy; **no app imports it**; realtime / upload throw "not implemented" |
| `zatgo_dart_sdk` (`SharedSDK/dart_sdk`) | 50 | vansalex 38, warehouse 6, customers 5, sync 1; used by 8 Flutter apps |
| **In neither** | **57** | MyBis 37, `accounting.payment_methods` 6, gym 4, `app_hub` 2, `language` 2, jewellery 2, `pos_settings.get`, `payments.party_balance`, `vansalex.health.status`, `vansalex.returns.pdf` |

Coverage by group (backend / TS erpnext / Dart): accounting 90 / 81 / 5, resto_pos 34 / 34 / 0, retail_pos 12 / 12 / 0,
vansalex 40 / 0 / 38, mybis 37 / 0 / 0, warehouse 16 / 14 / 6, delivery + config + settings + apps + devices 48 / 48 / 0.

Findings:

- "Generated" is nominal: the generate script (`scripts/generate_sdk.py`, `whitelist_methods.json`) does not exist. **No tests and no CI** in either SDK.
- Error handling differs: Dart throws `ZatGoApiError(code, message, details, requestId)`; the TS `envelope.ts:33` throws a plain `Error` and loses `code` and `request_id`; `ts-sdk` never checks `res.ok`; `api/v1/language.py` returns raw payloads that both unwrappers reject.
- Auth differs: Dart uses the `sid` cookie with no CSRF and flutter-vansalex sends writes by GET; TS keeps a cookie jar + CSRF; Next.js apps seal the cookie in eight per-app variants.
- Clients that bypass the SDK: **mybis** (`lib/data/datasources/mybis_api.dart` hard-codes `zatgo_core.api.v1.mybis.*`); `zatgo-pos` smoke scripts (dev only); `desktop-accounting` calls `frappe.client.get`.
- Duplication: the proxy / login routes and `lib/client.ts` are identical in 7 web apps; `call-zatgo-api.ts` in 8 web and 7 desktop apps; `web-bench-manager` vendors a stale copy of the UI package.
- Packaging: `pnpm-workspace.yaml` lists 3 of the 17 consumers; two `node_modules/@zatgo` symlinks dangle; 15 of 16 apps have a stale tailwind `@source` path.
- Six Flutter apps (delivery, chat-ai, tracker, service, kitchen, go-van) reference 59 constants the Dart SDK lacks, so they cannot compile (out of scope per `SharedSDK/CLAUDE.md`). Four `go_van.*` strings have no backend.

## 6. Design tokens (for the Settings Map)

Three blues are in use: **#2952E3** (Desk and website), **#2F5FEA** (VanSaleX and MyBis mobile), **#0E5794** (web / desktop
accounting). The Desk theme is optional (`enable_saas_theme`, off by default), so a new page defines its own `--zgs-*` tokens
with literal fallbacks and a `[data-theme="dark"]` block. The popup tile colour is a label hash (`events/boot.py::_TILE_COLORS`):
AI, VanSaleX, POS and General Settings all get #6366F1 and Tracker, Space and MyBis all get #3B82F6.

Proposed accents (accent / 12% tint / ink | dark; all >= 4.5:1 on white and on the dark card): VanSaleX #2F5FEA / #E6ECFC /
#26449A | #7C9BFF · MyBis #8430CE / #F0E6F9 / #5B2688 | #BB86FC · POS #308639 / #E6F0E7 / #265C2C | #5CD87D · ZatGo AI #0F766E /
#E2EFEE / #12524D | #2DD4BF · Tracker #1B4D3E / #E4EAE8 / #19382F | #4ADE80 · Space #4F46E5 / #EAE9FC / #3A3497 | #A5B4FC.
Status pills: Enforced #0B8C3E (solid), Read by client #2248CC (tint), Informational #697386 (hollow), Not wired yet #B76E00
(dashed). Scope pills: Site #475569, Company #0E7490, Branch #4D7C0F, User #C2255C, Device #C2410C.

## 7. Gaps and recommended follow-ups

Not fixed by this audit (each is its own change); ordered by value.

1. **Wire ZatGo POS to its settings.** Call `pos_settings.get` from `desktop/zatgo-pos` (and add `posSettings` / `posProfile` to `@zatgo/erpnext`), then **enforce** the discount cap, default warehouse / customer / payment mode and split payment in `services/resto_pos_service.py` and `services/retail_pos_service.py`.
2. **Currency and precision from the backend** (`vansalex.me.context`, `pos_profile.get`, `mybis.context`) instead of SAR / `$` / 2 decimals in the clients.
3. **MyBis:** the app must use `default_preset`, `week_start` and the currency; admin policy (refresh floor, severity floor, export formats, KPI cards, offline copy allowed) belongs in `ZG MyBis Settings`.
4. **Per-user theme and language** into `ZG User Preferences` and read by the clients; printer settings from `ZG Printer Settings`.
5. **SDKs:** add the 57 missing methods that clients need (`mybis`, `pos_settings`, `app_hub`, `language`, `payment_methods`) to both SDKs, keep `code` / `request_id` in TS errors, add the first envelope + session tests, fix `pnpm-workspace.yaml` and the `@source` paths, retire `@zatgo/sdk` or make it the real one, and give Flutter a shared theme package.
6. **Audit trail:** only the core settings controllers use `AuditableMixin`; VanSaleX, POS, Theme, Language, MyBis, Chat AI, Tracker, Space, Naming and the Van Sale Profile rely on `track_changes` versions.
7. **Branch scope:** resolve a user's branch on the server; `ZG Branch Settings` is advisory until then. `ZG Security` floors are not wired to Frappe's password / session policy.

## 7a. Which default wins (company and warehouse)

The same default lives in several places (see `docs/duplication_audit.md`); this is what the code actually reads, in order.

| Question | Entry point | Order |
|---|---|---|
| Company | accounting and POS services (`services/erpnext_writes.py::_default_company`, also used by the restaurant and retail POS) | the company passed in -> the user's default Company -> Global Defaults.default_company -> the first Company on the site -> error |
| Company | VanSaleX (`services/vansalex_settings.py::_user_company`) | the van warehouse's company -> the target user's default Company -> Global Defaults.default_company -> none. Deliberately **no** "first company" fallback |
| Company | MyBis (`api/v1/mybis/context.py`) | the user's default Company -> ZG MyBis Settings.default_company -> Global Defaults.default_company (only a company the user may read) |
| Company | Desk boot payload | ZG System Settings.default_company (informational; posting never reads it) |
| Warehouse | VanSaleX (`vansalex_settings.default_warehouse`) | the driver's van warehouse -> ZG Company Settings.default_warehouse -> Stock Settings.default_warehouse (only if it belongs to the company) -> none |
| Warehouse | restaurant and retail POS (`services/resto_pos_service.py::_resolve_pos_warehouse`) | ZG Company Settings.default_warehouse -> **the first enabled, non-group Warehouse of the company** -> error. `ZG POS Settings.default_warehouse` is not read |

## 8. Found while testing (2026-10-31)

- `services/retail_pos_service.py::_set_paid_to` called `payment_entry.get_bank_cash_account(mop, company)` although that helper takes `(doc, bank_account)`: every Supermarket sale failed at the payment step with `AttributeError: 'str' object has no attribute 'company'` (7 of 20 `test_retail_pos` tests). Fixed by passing a document-like `frappe._dict(company=..., mode_of_payment=...)`, as `services/erpnext_writes.py` does.
- On production the Supermarket and General Retail POS types are refused ("not available yet") until the retail-POS work ships; Restaurant and Cafe work. MyBis is not on production at all.
- Cafe equals Restaurant and General Retail equals Supermarket in features (`desktop/zatgo-pos/src/lib/verticals.ts` feature lists are identical): they differ only by label. The effect of the POS Type is the engine (restaurant vs retail).
