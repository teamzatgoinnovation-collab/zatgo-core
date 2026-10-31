# Changelog — ZatGo Core

## Unreleased

### Added — Settings Map (Desk page `zg-settings-map`)

- Every app's settings with real controls, editable in place: a switch for each Check, a choose-one group for a short Select (a dropdown for longer ones), number / link / text inputs, a set / not-set badge for secrets, a summary + "Open form" for tables and attachments. Each row carries a **scope** pill (Site, Company, Branch, User, Role, Device, Warehouse) and a **status** pill (Enforced, Read by client, Informational, Not wired yet); each app has a read-only "On the device" list per client app. Colourful per app (own `--zgs-*` tokens, dark mode, phone width first, reduced motion respected).
- `services/settings_map.py` (`describe`, `save_field`), `services/settings_notes.py` (status / scope / who enforces it, from `docs/settings_scope.md`), `services/settings_palette.py` (accent -> tint / ink / dark tokens, contrast >= 4.5:1), `api/v1/settings_map.py` (`get_map`, `save_field`). `save_field` accepts only DocTypes listed in an app manifest, needs write permission on the DocType, refuses hidden / read-only / Password / Table / Attach fields and the app switches (those go through `app_hub.set_switch`), and saves through `doc.save()` so controller validation and the audit trail run.
- New manifest keys `color`, `scoped`, `clients`, `device` (validated in `services/app_catalog.py`). The ZatGo popup tiles use each app's accent instead of a label hash. The apps hub cards got a **Configure** link.
- `AuditableMixin` on VanSaleX, POS, Theme, Language and MyBis settings.
- Fixed: the *Apps (on / off)* tile was missing from the ZatGo workspace page (its content block named the shortcut "ZatGo Apps"). Added the *Settings Map* shortcut.
- MyBis files touched (`mybis/app_manifest.py`, `ZG MyBis Settings`) are not on the Hetzner server: keep them out of any delta.

### Added — Supermarket industry: the retail POS engine

- **Supermarket** is an implemented industry: `api/v1/retail_pos/` (catalog, stock, customers, payments, dashboard, one-step `sale.create`) over `services/retail_pos_service.py`. A sale posts ONE submitted Sales Invoice (`update_stock=1`, server-owned tax, cashier discount on the invoice) plus a Payment Entry for the chosen Mode of Payment (idempotent on `client_id` and `client_id:pay`); a card / wallet / bank mode lands in its own account with the invoice number and date as the bank reference. The API answers 404 while the industry or the ZatGo POS app is off.
- `pos_profile.get` now returns `pos_mode`, `pos_type`, `pos_vertical`, `retail` next to `restaurant`; the POS Type of ZG POS Settings decides, else the industries (Restaurant first).
- Tests: `test_retail_pos` (20) and `test_pos_type_effect` (every POS type runs a real sale through its engine, switching never switches the other industry off). Not on production until deployed: there the Supermarket and General Retail POS types are refused ("not available yet").

### Added — settings scope audit

- **`docs/settings_scope.md`**: where every app is configured, at which scope (site / company / branch / user / role / device), who edits it, whether the server enforces it, what the client apps keep on the device, the shared-SDK coverage (334 backend methods; 57 in neither SDK) and the gaps, ordered. Found while testing the POS types: ZG POS Settings other than `pos_type` is served but read by no client and enforced by no server code.

### Changed — every app owns its settings; the ZatGo popup lists the apps that are on

- **The ZatGo folder lists only apps switched on** (plus General Settings); each opens its own sidebar. **General Settings** starts with *Apps (on / off)* (the hub), where every app is switched on or off. Desk Theme, Language Switcher, VanSaleX Web and MyBis are apps like the rest now, with a Workspace and a sidebar of their own.
- **New settings forms**: `ZG Theme Settings` (brand name, logo, theme), `ZG Language Settings` (default language), `ZG MyBis Settings` (default company and period of the dashboards). `brand_name`, `company_logo`, `theme` and `language` leave ZG System Settings (hidden there; `patches/v0_4_10` copies the stored values; `services/ui_settings.py` is what readers use, same API keys as before). On/off switches stay in ZG System Settings.
- **POS Type** also offers Cafe (restaurant engine) and General Retail (supermarket engine); Pharmacy and Electrical are listed as coming soon and cannot be saved. `pos_settings.get` returns `pos_vertical` (restaurant | cafe | supermarket | general); the desktop POS follows it.
- Needs `bench migrate` on each site.

### Added — POS Type in ZG POS Settings

- **POS Type** (Restaurant / Supermarket) on ZatGo POS -> POS Settings -> General: the choice the desktop POS app used to make in its own setup now lives in the backend. It decides the `pos_mode` the POS gets (`pos_settings.get` returns `pos_type` and `pos_mode`). Saving a type switches the matching industry on (never the other off); changing it is a System Manager's call, like any industry switch. Left empty (every existing site), the industries decide as before, Restaurant first. The ZatGo folder on the Apps screen now lists every app (AI, Tracker, Space, MyBis, Desk theme, language switcher, VanSaleX web too); one with no sidebar to open sends a System Manager to the App Settings Hub.

### Changed — ZatGo Desk layout (apps with tabs)

- **Each app opens in its own sidebar** (like Banking in ERPNext) from the ZatGo folder on the Apps screen: Overview, Settings (one item per settings tab), then the app's own groups -- replaces the tabbed `/desk/zg-app/<app>` page (Page `zg-app`, its API and `zg_app_tabs.js` removed; old URLs redirect to the app's Workspace). The ZatGo sidebar is now General Settings only. `services/app_sidebar.py`.
- **The ZatGo sidebar has two sections**: *Apps* (one entry per enabled app and industry) and *General Settings* (the app hub, the platform settings, the Desk theme / language switcher / VanSaleX web switches). An app's own settings are no longer sidebar entries.
- **Each app opens a page with tabs** (`/desk/zg-app/zatgo-<app>`, new Page `zg-app`, `api/v1/app_page.py`): *Overview* (the app's shortcuts and cards, per-user filtered) and one tab per settings topic. Settings forms are split into Tab Breaks -- VanSaleX Settings (Payments / Sales & Warehouse / Modules & Features), Chat AI Settings (Provider / Conversation / Safety & Tools / Features / Voice & Files / Costs; sections reordered, fields unchanged), Tracker and Space Settings, and ZG System Settings (General / ERP Behaviour / Apps / Industries). Field names and stored values are untouched.
- Every app's own rail icon is hidden (apps open from ZatGo → Apps); Workspaces are kept. Old `/desk/zatgo-ai`-style URLs redirect to the page. ZatGo Space gets a Workspace (it had none).
- Needs `bench migrate` on each site (DocType layout, the page, the sidebar, the icon flags).

### Security (2026-10-24, audit H3/H4/H5)

- **Chat AI tool calls are guarded** (`chat_ai/core/tool_sources/net.py`): REST tools, MCP servers, integration connectors and their health checks call out only over http(s), with a fixed host in the URL template, never to metadata / link-local addresses, pinned to the checked address, without following redirects, with a 1 MB response cap. The connector's "read" tool is GET/HEAD only -- POST/PUT/PATCH/DELETE is a separate tool the user confirms; an MCP tool needs confirmation unless its server marks it `readOnlyHint`. URLs are validated when saved.
- **Reads respect User Permissions** (`services/row_scope.py`): the shared list helpers, the accounting dashboard and reports, and the Tracker task/project lists use `get_list`; SQL sums add the user's Company restriction; `profit_and_loss` accepts a `company`; a portal (Website User) session sees only its own Customer's / Supplier's orders. The dashboard reads each ledger once instead of four times.
- The delivery, fleet, service-ticket and restaurant DocTypes grant `Desk User` (every System User) instead of `All` (every logged-in user, portal users included).

### Changed — app platform (audit 2026-10-23, `docs/audit_2026-10-23.md`)

- **ZatGo VanSaleX is a real app switch**: ZG System Settings → "Enable ZatGo VanSaleX" (default on; a site with no
  stored value counts as on; patch `v0_4_7` stores the 1). Off: the VanSaleX API (`zatgo_core.api.v1.vansalex.*`)
  answers 404, it leaves the ZatGo sidebar, its workspace and rail icon are hidden; data untouched. The VanSaleX
  Web page follows it (`enable_vansalex_web` now requires it).
- **Switching apps or industries is System Manager only on every route** (was: also ZG Company Admin / ZG
  Application Admin through the form or REST). Enforced in the ZG System Settings controller
  (`services/app_authority.py`); an app cannot be on while one it `requires` is off.
- Manifest v2 (all optional): `version`, `requires`, `api_prefixes`, `default_on`; new group `app`. New
  `services/app_state.py` (is app X on), `services/app_gate.py` (API 404, `@app_api`, `require_app`),
  `services/app_desk.py`. `services/ui_apps.switches` still works (re-exported).
- **Plugin registry**: the catalog-derived rows were rejected by the `category` Select and never registered; they
  now register with the real enabled state and version, a re-run changes nothing and writes no history, an
  admin's edit of `visible`/`roles`/`menu_order` survives a migrate, and VanSaleX has one entry (title
  "ZatGo VanSaleX").
- **ZatGo Apps** page (`zg-app-hub`, was "App Settings Hub"): summary, version, requirements, warnings, skipped
  manifests, accessible switches, responsive/dark-mode layout; routes `/desk/…`.
- Config API: `seed_bundled_manifests`, `export_settings`, `get_dashboard` need a manager; `save_settings` only
  accepts ZatGo settings DocTypes and derives its guard category itself (the `category` argument is ignored);
  Singles listed by an app manifest (VanSaleX Settings, …) are reachable by the config API; a section's Single
  needs its own read permission.
- `ZG Device Token` and `ZG User Preferences` are limited to their owner on every route (REST, Desk).
- Turning the language switcher on from the hub now enables Arabic at once; the two dead buttons on ZG System
  Settings ("Clear ZatGo Cache", "Refresh App Registry") work.
- `AppRegistryService.is_client_enabled` says no for a client product whose ZatGo app is switched off; Desk boot
  carries `bootinfo.zatgo_core.apps` (the enabled apps) for Desk scripts.
- Chat AI: its all-DocTypes re-index hook no longer indexes `AI Search Index` and log-like tables (a latent loop
  once document events + vector search were both on). Indexes added on the columns Chat AI and VanSaleX trips
  filter by (`AI Usage Daily` user/date, `AI Chat Message` session, `AI Chat Session` user, `AI Tool Log`,
  `AI Attachment` session, `ZG Trip` sales user/status/planned at) -- built by the next migrate.
- `ZG Delivery Boy` creation validated its vehicle against `ZG Vehicle` (nulling ERPNext `Vehicle` names).
- Branding: Desk app title is "ZatGo"; admin messages no longer say "zatgo_core". `docs/naming.md` and
  `tests/unit/test_naming_standard.py` (new DocTypes are `ZG <Name>`; 25 legacy names kept).
- Docs: architecture, folder structure, DocTypes (all 68), permissions, plugin guide rewritten to match the code.
  `scripts/generate_doctypes.py`, `fix_controllers.py`, `generate_reports.py` refuse to run (they overwrite
  hand-edited files). `setup.py` version and `MANIFEST.in` fixed.

- ZG System Settings → "Stock Summary: only warehouses with stock" (default on): off lists all warehouses.

- Warehouse custom field `zg_vansalex_selectable` ("Selectable Warehouse"): warehouse dropdowns (sales/purchase forms, VanSaleX picker)
  offers only ticked warehouses (plus the user's default, preselected); none ticked = all sellable, as before.
  Patch `v0_4_1.add_warehouse_selectable_field`.

## 0.4.0 — 2026-10-15

### Added

- Multi-industry layer (`zatgo_core/industries/`): registry of 17 industries, per-site switch in
  ZG System Settings → Industries, server-side gating (API 404, DocType permissions, jobs), dependency validation.
  Pilots: Restaurant (gates existing Resto POS), Jewellery, Gym. See `docs/industries.md`.
- DocTypes `ZG Enabled Industry`, `ZG Gym Plan`, `ZG Gym Membership`, `ZG Gym Attendance`, `ZG Metal Rate`;
  Item custom fields `zg_jewellery_*` (hidden unless Jewellery is on).
- Patches: `v0_4_0.create_industry_roles` (pre-model-sync), `v0_4_0.enable_restaurant_where_used`.

- Textile industry ready: Item fields `zg_textile_*` (hidden unless Textile is on), workspace; variants via ERPNext attributes.

### Changed

- Version aligned to 0.4.0 across `hooks.py`, `__init__.py`, `pyproject.toml`.


## 0.2.2 — 2026-07-22

### Removed

- Hub facade `zatgo_core.api.v1.chat_ai.*` — Chat AI clients use `chat_ai.api.*`
  on the `chat_ai` domain app

### Changed

- Docs: hub is for client apps **except** Tracker (`tracker.api.v1.*`) and
  Chat AI (`chat_ai.api.*`), which own ERPNext domain APIs

## 0.2.1 — 2026-07-21

### Removed

- Desk UI: page `zg-core`, Core Administration workspace, desktop icon / sidebar,
  script reports, number cards, dashboards, and Desk `app_include` JS/CSS
- `setup/ensure_desktop.py` and `config/desktop.py`

### Changed

- Hub is **API + settings DocTypes only** (client RPC / platform framework)
- Install / migrate purge legacy Desktop Icon, Workspace Sidebar, Page leftovers

## 0.2.0 — 2026-07-16

### Added

- Plugin registry DocTypes: `ZG Registered Application`, `ZG Setting Section`,
  `ZG Config Profile`, `ZG Config History`
- Manifest registration + bundled POS / Delivery / Kitchen samples
- APIs under `zatgo_core.api.v1.config.*`
- [Plugin author guide](plugin_guide.md)

## 0.1.0 — 2026-07-16

### Added

- Foundation DocTypes (`ZG *` settings, registry, flags, audit, preferences)
- Clean architecture packages: api / services / repositories / cache / validation / permissions
- Whitelisted REST-style methods for settings, flags, apps, integrations, health
- Roles: ZG Company Admin, Branch Admin, Application Admin, Read Only
- Install / migrate seeds, hourly app registry sync, boot_session payload
- Unit / API contract / permission matrix tests
- Developer documentation suite
