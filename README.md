# ZatGo Core

ERPNext / Frappe foundation application (`zatgo_core`).

This is the **single ZatGo platform app** on ERPNext:

- Settings foundation (system / company / branch, flags, integrations, security)
- Site Application Settings for Electron / Flutter / Web clients
- Product client RPC hub: `zatgo_core.api.v1.<product>.*`
- Shared ZG DocTypes (delivery, KDS, fleet stubs, …)

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

## Install (development)

```bash
./scripts/install_custom_apps.sh development <site> zatgo_core
```

## Workspace / Config Center

Desk → **ZatGo Core** icon → sidebar **Home** opens page **`zg-core`**
(plugin configuration center).

See [Plugin author guide](docs/plugin_guide.md).

## Naming note

DocTypes use the `ZG` prefix (for example `ZG System Settings`) to avoid
colliding with Frappe / ERPNext built-ins such as `System Settings`.
# zatgo-core
