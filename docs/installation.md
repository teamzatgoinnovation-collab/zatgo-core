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

1. Open Desk → **Core Administration**
2. Configure **ZG System Settings** (brand, default company, timezone)
3. Open **ZG Application Settings** → Seed Default Clients
4. Review **ZG Feature Flag** defaults
5. Set **ZG Security Settings** password / session policy
6. Assign roles: ZG Company Admin / Branch Admin / Application Admin / Read Only

## Install order for dependent apps

```text
frappe → erpnext → zatgo_core → optional product apps
```

Do **not** install `zatgo_api` (merged into `zatgo_core`).

Product apps should declare:

```python
required_apps = ["erpnext", "zatgo_core"]
```
