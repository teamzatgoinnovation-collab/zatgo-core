# Architecture — ZatGo Core

## Role in the ecosystem

`zatgo_core` is the **API-only platform hub** for most client apps
(settings + `zatgo_core.api.v1.<product>.*` RPC). It has no Desk module UI.

**Not routed through this hub:** Tracker (`tracker.api.v1.*`) and Chat AI
(`chat_ai.api.*`) — full domain apps under `CustomApps/erpnext/` with their
own DocTypes, Desk, and APIs.

```text
Most Flutter / Electron / Web clients
            │
            ▼
   ┌────────────────────────────────────┐
   │            zatgo_core              │
   │  settings + api/v1/<product> RPC   │
   └────────────────────────────────────┘
            │
            └── ERPNext / Frappe

Tracker / Chat AI clients ──► tracker / chat_ai domain apps ──► ERPNext
```

`zatgo_api` was merged into `zatgo_core`. Prefer hub paths for products that
do not yet own a domain package; never duplicate Tracker or Chat AI RPC here.

No product app should duplicate global/company/branch settings, feature flags,
integration credentials, printer defaults, or number series. They must read from
`zatgo_core` services / APIs (including Tracker / Chat AI for shared settings).

## Clean architecture layers

| Layer | Package | Responsibility |
|-------|---------|----------------|
| API | `zatgo_core.api.v1.*` | Whitelisted RPC, response envelope |
| Services | `zatgo_core.services.*` | Business orchestration |
| Repository | `zatgo_core.repositories.*` | Document persistence |
| Cache | `zatgo_core.cache.*` | Redis + invalidation |
| Validation | `zatgo_core.validation.*` | Domain rules |
| Permissions | `zatgo_core.permissions.*` | Role / company scope |
| Events | `zatgo_core.events.*` | boot_session, doc hooks |
| Mixins | `zatgo_core.mixins.*` | Audit + cache-on-update |
| Constants | `zatgo_core.constants.*` | DocType names, roles, cache keys |
| DocTypes | `zatgo_core.zatgo_core.doctype.*` | Persistence model |

## Design decisions

1. **ZG prefix** — avoids clashes with Frappe `System Settings` and similar.
2. **Singles vs lists** — truly global config is Single; company/branch/user/
   registry/flags/audit are list DocTypes (enterprise multi-tenant reality).
3. **Audit mixin** — every settings mutation writes `ZG Audit Log` (passwords redacted).
4. **Cache-first reads** — services use Redis via `CacheManager` + `frappe.get_cached_doc`.
5. **Auto registry sync** — hourly scheduler + install hook scans installed apps.

## Runtime flow (settings read)

```text
Client → whitelisted API → SettingsService → CacheManager
                                      ↓ miss
                               SettingsRepository → DocType / MariaDB
                                      ↓
                               Redis set + return envelope
```
