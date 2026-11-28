# Installation Guide — ZatGo Core

## Prerequisites

- Frappe 16.x and ERPNext 16.x (tested: Frappe 16.29, ERPNext 16.31). `before_install` refuses any other major version.
- MariaDB, Redis
- Python ≥ 3.11

## Development bench

From the monorepo root:

```bash
./scripts/install_custom_apps.sh development <site> zatgo_core
```

Manual equivalent (from GitHub, or a local path instead of the URL):

```bash
bench get-app https://github.com/teamzatgoinnovation-collab/zatgo-core.git
bench --site <site> install-app zatgo_core
bench --site <site> migrate
bench build --app zatgo_core
bench --site <site> clear-cache
```

## What install refuses
- A Frappe or ERPNext major version other than 16.
- A site where another app already owns one of ZatGo's DocType names (they are plain names, ADR-005). The error names
  each clash (`install.doctype_name_collisions`).

## Post-install checklist
Install creates, once: the ZatGo roles and Role Profiles (personas), the module workspaces, Module Settings rows
and the ZatGo Settings landing page. A re-run or migrate never overwrites what an administrator changed.

1. **Module Settings**: switch off the ZatGo modules this site does not use (data is kept; the API answers 404).
2. **ZatGo Apps** (Desk → ZatGo → Apps): switch on the apps and industries this site needs (System Manager only).
3. **ZatGo Settings** workspace: ERPNext's own settings first (System Settings, Global Defaults, Company, Selling,
   Stock, Accounts), then ZatGo's (Company Settings, Sales Invoice Naming, VanSaleX, POS). See `SETTINGS.md`.
4. Tax: mark one **Sales Taxes and Charges Template** per company as default (or choose it in Company Settings),
   and one Purchase template if purchases carry VAT. Invoices from every ZatGo path use it.
5. Users: give each a Role Profile (User → Role Profiles) and, where needed, User Permissions
   (`restrict_user`, see `permissions.md`).
6. Confirm `bench --site <site> list-apps` includes `zatgo_core`.

## Uninstall
`bench --site <site> uninstall-app zatgo_core` drops every ZatGo DocType **and its data** (orders, trips, audit
log, settings). ERPNext's own documents stay. Take a backup first (`bench --site <site> backup --with-files`);
never use `--no-backup` on a site with real data. To stop using ZatGo features without losing data, switch the
modules off in Module Settings instead.

## Install order for dependent apps

```text
frappe → erpnext → zatgo_core → optional product apps
```

Do **not** install `zatgo_api` (merged into `zatgo_core`).

Product apps should declare:

```python
required_apps = ["erpnext", "zatgo_core"]
```
