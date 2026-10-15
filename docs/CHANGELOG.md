# Changelog — ZatGo Core

## 0.4.0 — 2026-10-15

### Added

- Multi-industry layer (`zatgo_core/industries/`): registry of 17 industries, per-site switch in
  ZG System Settings → Industries, server-side gating (API 404, DocType permissions, jobs), dependency validation.
  Pilots: Restaurant (gates existing Resto POS), Jewellery, Gym. See `docs/industries.md`.
- DocTypes `ZG Enabled Industry`, `ZG Gym Plan`, `ZG Gym Membership`, `ZG Gym Attendance`, `ZG Metal Rate`;
  Item custom fields `zg_jewellery_*` (hidden unless Jewellery is on).
- Patches: `v0_4_0.create_industry_roles` (pre-model-sync), `v0_4_0.enable_restaurant_where_used`.

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
