# ZatGo Core

**ZatGo** for ERPNext / Frappe — the supporting app (`zatgo_core`) on top of ERPNext: the customisations ERPNext
does not ship, and the platform that switches ZatGo's apps on and off per site.

- **Apps**: VanSaleX, Tracker, ZatGo AI, ZatGo Space, industries and Desk add-ons, each switched per site in
  **ZatGo Apps** (Desk → ZatGo); off hides the app and makes its API answer 404, data is never touched
- Settings foundation (system / company / branch, flags, integrations, security)
- Application registry + client app settings for Flutter / Electron / Web clients
- Product client RPC hub: `zatgo_core.api.v1.<product>.*`
- Shared ZG DocTypes (delivery, KDS, fleet stubs, …)

**Bundled modules (merged 2026-10-08):** Chat AI, Tracker and ZatGo Space (`zatgo_core/chat_ai`, `/tracker`,
`/zatgo_space`), the SaaS Desk theme and the language switcher are modules of this app, each switched per site in
ZG System Settings (`services/bundled_apps.py`, `services/ui_apps.py`). Their old separate apps are archived.

**Industries:** optional industry modules (Restaurant, Jewellery, Gym, Textile ready; 13 more registered) are switched per site in
ZG System Settings → Industries — see [`docs/industries.md`](docs/industries.md).

**Desk UI:** the generated "ZatGo" sidebar lists the apps a site has switched on (Overview + settings for each) and
the ZatGo Apps page is where they are switched; workspaces exist for VanSaleX and for bundled modules /
industries a site has switched on.

`zatgo_api` was merged into this app — do not install it separately.

## Docs

- [Architecture](docs/architecture.md)
- [Naming standard](docs/naming.md)
- [Audit 2026-10-23](docs/audit_2026-10-23.md)
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
colliding with Frappe / ERPNext built-ins such as `System Settings`; the Python package stays `zatgo_core`
(see [`docs/naming.md`](docs/naming.md)).
