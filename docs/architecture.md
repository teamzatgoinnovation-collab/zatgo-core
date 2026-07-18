# Architecture — ZatGo Core

## Role in the ecosystem

`zatgo_core` is the foundation layer of the ZatGo ERP platform.

```text
Flutter / Electron / Desk / Web clients
            │
            ▼
   ┌────────────────────────────────────┐
   │            zatgo_core              │
   │  settings + api/v1/<product> RPC   │
   └────────────────────────────────────┘
            │
            ├── optional product domain apps
            └── ERPNext / Frappe
```

`zatgo_api` was merged into `zatgo_core`. Client RPC paths are
`zatgo_core.api.v1.<product>.*`.

No product app should duplicate global/company/branch settings, feature flags,
integration credentials, printer defaults, or number series. They must read from
`zatgo_core` services / APIs.

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
