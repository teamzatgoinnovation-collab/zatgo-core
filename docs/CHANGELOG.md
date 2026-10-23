# Changelog — ZatGo Core

## Unreleased

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
