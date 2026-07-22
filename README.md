# ZatGo Core

ERPNext / Frappe **API-only platform hub** (`zatgo_core`) for client apps
(Flutter / Electron / Web):

- Settings foundation (system / company / branch, flags, integrations, security)
- Site Application Settings + application registry for clients
- Product client RPC hub: `zatgo_core.api.v1.<product>.*`
- Shared ZG DocTypes (delivery, KDS, fleet stubs, …) until each product owns a domain app under `CustomApps/erpnext/<Product>/`

**Exceptions — own domain APIs (not this hub):**

| Product | Package | Client RPC |
|---------|---------|------------|
| Tracker | `tracker` (`CustomApps/erpnext/Tracker`) | `tracker.api.v1.*` |
| Chat AI | `chat_ai` (`CustomApps/erpnext/ChatAI`) | `chat_ai.api.*` |

Those apps live on ERPNext with their own DocTypes + Desk + whitelist APIs.
Clients for Tracker / Chat AI call those packages directly; do not add
`zatgo_core.api.v1.tracker` or `zatgo_core.api.v1.chat_ai` facades.

**No Desk module UI** — no pages, workspaces, desktop icons, reports, or dashboards. Operators edit settings DocTypes via AwesomeBar / List when needed.

`zatgo_api` was merged into this app — do not install it separately.

## Docs

- [Architecture](docs/architecture.md)
- [Folder Structure](docs/folder_structure.md)
- [DocTypes](docs/doctypes.md)
- [API Reference](docs/api.md)
- [Permission Matrix](docs/permissions.md)
- [Installation Guide](docs/installation.md)
- [Upgrade Guide](docs/upgrade.md)
- [Developer Guide](docs/developer.md)
- [Deployment](docs/deployment.md)
- [Changelog](docs/CHANGELOG.md)

## Install

Push this app to its own git remote, then on a stock frappe_docker bench ([`ERPNEXT/README.md`](../../ERPNEXT/README.md)):

```bash
bench get-app https://github.com/<org>/zatgo_core.git
bench --site <site> install-app zatgo_core
bench --site <site> migrate
```

See [Plugin author guide](docs/plugin_guide.md) for registering client/plugin manifests via API.

## Naming note

DocTypes use the `ZG` prefix (for example `ZG System Settings`) to avoid
colliding with Frappe / ERPNext built-ins such as `System Settings`.
