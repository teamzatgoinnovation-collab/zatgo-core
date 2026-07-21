# Changelog — ZatGo Core

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
