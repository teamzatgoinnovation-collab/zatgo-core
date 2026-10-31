# Installation Guide — ZatGo Core

## Prerequisites

- Frappe latest stable
- ERPNext latest stable
- MariaDB, Redis
- Python ≥ 3.11

## Development bench

From the monorepo root:

```bash
./scripts/install_custom_apps.sh development <site> zatgo_core
```

Manual equivalent:

```bash
bench get-app /absolute/path/to/CustomApps/ZatGoCore
bench --site <site> install-app zatgo_core
bench --site <site> migrate
bench build --app zatgo_core
bench --site <site> clear-cache
```

## Post-install checklist

ZatGo Core has **no Desk module**. Use AwesomeBar / List, or client APIs:

1. Switch on the apps and industries this site needs in **ZatGo -> Apps (on / off)** (they are fields of ZG System Settings). Brand, logo and theme are in **ZG Theme Settings**. The default company, timezone, country, currency and fiscal year are ERPNext's own: **Global Defaults** and **System Settings** (the same-named fields of ZG System Settings, where they still exist, are not read; see `duplication_audit.md`)
2. Open **ZG Application Settings** → Seed Default Clients (or call apps API)
3. Review **ZG Feature Flag** defaults
4. Set the password and session policy in Frappe's **System Settings**. **ZG Security Settings** is only validated, nothing applies it yet
5. Assign roles: ZG Company Admin / Branch Admin / Application Admin / Read Only
6. Confirm `bench --site <site> list-apps` includes `zatgo_core`; hard-refresh Desk if an old Core icon remains

## Install order for dependent apps

```text
frappe → erpnext → zatgo_core → optional product apps
```

Do **not** install `zatgo_api` (merged into `zatgo_core`).

Product apps should declare:

```python
required_apps = ["erpnext", "zatgo_core"]
```
