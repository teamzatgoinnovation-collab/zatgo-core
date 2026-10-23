# Architecture — ZatGo Core

## Role in the ecosystem

ERPNext is the accounting/inventory engine. **ZatGo Core (`zatgo_core`) is the supporting app on top of it**:
the customisations ERPNext does not ship, a client RPC hub (`zatgo_core.api.v1.<product>.*`), and the
platform that switches ZatGo's apps on and off per site. User-facing it is simply **ZatGo**.

```text
Flutter / Electron / Web clients ──► zatgo_core.api.v1.*  ──► services ──► ERPNext (GL, stock ledger)
Desk users ───────────────────────► ZatGo workspace / sidebar / ZatGo Apps page
```

Real financial writes always go through ERPNext's own document controllers; nothing here posts to the GL or
stock ledger by itself (see `.claude/rules/accounting.md`).

## The app platform

zatgo_core is installed on every accounting / van-sale site, so everything optional must be **inert unless
switched on**. That is one mechanism, driven by one catalog:

```text
app manifest ──► app_catalog ──┬─► app_state   is app X on? (ZG System Settings switches)
 (per app)       (normalised)  ├─► app_gate    API of an app that is off answers 404; @app_api; require_app
                               ├─► hub page    "ZatGo Apps": state, version, warnings, settings links, switch
                               ├─► sidebar     the generated "ZatGo" Desk sidebar
                               └─► registry    ZG Registered Application (client apps) — a one-way projection
```

- **Manifest** — `<module>/app_manifest.py` (`APP = {...}`) for a module folder, or an entry of
  `plugins/manifests/core_apps.py` for apps that live in the core module. Keys: `key`, `label`, `group`, `icon`,
  `description`, `switch_field`, `default_on`, `module_def`, `workspaces`, `settings`, `roles`, `version`,
  `requires`, `api_prefixes` (documented in `services/app_catalog.py`). Groups: `app` (in-core, e.g. VanSaleX),
  `bundled` (module with its own DocTypes: Chat AI, Tracker, ZatGo Space), `ui` (Desk add-ons), `core`,
  `industries`.
- **Four different questions** — *installed* (the code is there), *enabled* (the site's switch), *permitted*
  (the user's role / DocType permissions), *feature enabled* (an app's own catalog, e.g. VanSaleX modules &
  features). They are checked at different places and never confused: an app that is on is still limited by
  the user's permissions, and a feature that is off is off for admins too.
- **Off is not uninstalled.** Switching an app off hides it and makes its API answer 404; its tables, records,
  roles and settings stay untouched, and switching on again restores everything.
- **Who may switch.** A System Manager only — enforced in the ZG System Settings controller
  (`services/app_authority.py`), so the Desk form and the REST API are bound as well as the hub page. Every
  switch change is in the audit log.
- **Registry vs catalog.** The catalog is the truth for the apps this package ships. The plugin registry
  (`ZG Registered Application` + `ZG Setting Section`) is rebuilt from it (and from the hand-written manifests
  of apps the catalog does not own) with the site's real enabled state and version; an admin's edit of
  `visible` / `roles` / `menu_order` survives a migrate, the switch always wins for `enabled`.
- **Client apps** (`ZG Application Settings.client_apps`, Electron/Flutter/Web products) are a different thing:
  which front-ends may talk to this site. Their flags are advisory for the client; the server-side gate above
  is what enforces an app being off.

See `plugin_guide.md` for adding an app, `naming.md` for names, `permissions.md` for roles.

## Clean architecture layers

| Layer | Package | Responsibility |
|-------|---------|----------------|
| API | `zatgo_core.api.v1.*` | Whitelisted RPC, response envelope — thin |
| Services | `zatgo_core.services.*` | Business orchestration, the app platform |
| Repository | `zatgo_core.repositories.*` | Document persistence |
| Cache | `zatgo_core.cache.*` | Redis + invalidation |
| Validation | `zatgo_core.validation.*` | Domain rules |
| Permissions | `zatgo_core.permissions.*` | Role / company / owner scope |
| Events | `zatgo_core.events.*` | boot_session, doc hooks |
| Mixins | `zatgo_core.mixins.*` | Audit + cache-on-update |
| Constants | `zatgo_core.constants.*` | DocType names, roles, cache keys |
| DocTypes | `zatgo_core.zatgo_core.doctype.*` | Persistence model |

## Design decisions

1. **ZG prefix** — avoids clashes with Frappe `System Settings` and similar (`naming.md`).
2. **Singles vs lists** — truly global config is Single; company/branch/user/registry/flags/audit are lists.
3. **Audit mixin** — every settings mutation writes `ZG Audit Log` (passwords redacted).
4. **Cache-first reads** — services use Redis via `CacheManager` + `frappe.get_cached_doc`.
5. **One rule per concern** — app state in `app_state`, gating in `app_gate`, switch authority in
   `app_authority`; hooks and endpoints ask there instead of re-deriving.
6. **Desk assets per request** — site-optional JS/CSS is added by a `before_request` hook, never
   `app_include_*` (which loads on every site).
