# Changelog — ZatGo Core

## 0.2.0 — 2026-07-16

### Added

- Plugin configuration center: `ZG Registered Application`, `ZG Setting Section`,
  `ZG Config Profile`, `ZG Config History`
- Manifest registration + bundled POS / Delivery / Kitchen samples
- APIs under `zatgo_core.api.v1.config.*`
- Desk page `zg-core` (Vue 3 shell) with dashboard, applications tree, section host
- Desktop sidebar Home → `zg-core`
- [Plugin author guide](plugin_guide.md)

## 0.1.0 — 2026-07-16

### Added

- Foundation DocTypes (`ZG *` settings, registry, flags, audit, preferences)
- Clean architecture packages: api / services / repositories / cache / validation / permissions
- Whitelisted REST-style methods for settings, flags, apps, integrations, health
- Core Administration workspace, number cards, system health dashboard, script reports
- Roles: ZG Company Admin, Branch Admin, Application Admin, Read Only
- Install / migrate seeds, hourly app registry sync, boot_session payload
- Unit / API contract / permission matrix tests
- Developer documentation suite
