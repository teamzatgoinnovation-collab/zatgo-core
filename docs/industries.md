# Industries

zatgo_core is **core** (accounting, stock, sales, purchase, items — ERPNext's own engine) plus
**industry modules** that extend it. Each Frappe site chooses its industries; nothing is on by default.

```
CORE (always)  +  industries this site switched on  =  what the site exposes
```

## Where things live

| Piece | File |
|---|---|
| Registry (what exists, dependencies, roles, DocTypes, API prefixes) | `zatgo_core/industries/registry.py` |
| Per-site state + enforcement | `zatgo_core/industries/gate.py` |
| Roles / custom fields / Desk entries on switch | `zatgo_core/industries/sync.py`, `industries/<key>/setup.py` |
| Site switch (stored in the site DB) | `ZG System Settings` → **Industries** (child table `ZG Enabled Industry`) |
| Industry logic / API | `industries/<key>/service.py`, `api/v1/<key>/*.py` |

State is in the site database (so it survives restart, migrate, update, backup/restore); no industry
is named in `site_config.json` or hard-coded in `hooks.py`.

## Enabling / disabling

Desk → ZG System Settings → Industries → tick the industry → Save. Requires System Manager,
ZG Application Admin or ZG Company Admin. Saving validates the combination (unknown or not-yet-available
industry, missing core module, missing industry dependency are rejected), creates the industry's roles
and custom fields, and adds its workspace / sidebar / desktop icon. Unticking removes the Desk entries,
hides the custom fields and shuts the API; **data, DocTypes, roles and custom fields are never deleted**.

## What "enabled" means (enforced on the server)

Effective access = **Frappe role permission AND industry enabled** (a user permission still narrows it).

- Whitelisted methods under an industry's `api_prefixes` answer **404** while it is off (`before_request`).
- Its DocTypes are nobody's while it is off (`has_permission` / `permission_query_conditions` `"*"` hooks).
  Administrator and migrate bypass, as with the bundled modules.
- Industry API methods use `@frappe.whitelist()` + `@industry_api(key, roles=(...))`: login → industry on → role → DocType
  permission checks inside the service.
- Scheduled jobs start with `guard_job(key)`.
- The UI gets `frappe.boot.zatgo_core.industries` — a hint only.
- Everything fails closed: unreadable settings = every industry off.

## Status

| Industry | Status |
|---|---|
| Restaurant | Ready — gates the existing Resto POS (`api/v1/resto_pos`, ZG Table / ZG Order / ZG KDS Ticket). On upgrade, sites that already hold Resto data get it switched on by `patches/v0_4_0/enable_restaurant_where_used`. |
| Jewellery | Ready — Item fields (metal, purity, gross / stone / net weight, making charge, wastage, hallmark), `ZG Metal Rate`, price API. Barcodes, sale, purchase and return use the standard Item barcodes and invoices. |
| Gym | Ready — `ZG Gym Plan`, `ZG Gym Membership` (members are Customers; end date, renewal, billing through Sales Invoice with an idempotent `zatgo_client_id`), `ZG Gym Attendance`. |
| Textile, Supermarket, Salon, Electrical, Retail, Wholesale, Distribution, Pharmacy, Electronics, Hardware, Mobile, Automobile, Service, Manufacturing | Registered, **not implemented** ("Coming soon"); cannot be switched on. |

## Add a new industry — example: Pharmacy

1. **Module**: create `zatgo_core/industries/pharmacy/` (`__init__.py`, `service.py`, optional `setup.py`
   with `enable()` / `disable()` for custom fields — use `create_custom_fields` and
   `sync.set_custom_fields_hidden`). Reuse ERPNext DocTypes (Item batch/expiry) before adding DocTypes;
   a new DocType goes in `zatgo_core/zatgo_core/doctype/` with additive schema only.
2. **Register**: edit the `pharmacy` entry in `registry.py` — set `implemented=True`, `roles`, `doctypes`,
   `api_prefixes`, `workspace_links`, `features`.
3. **Dependencies**: `requires` (core capabilities such as `stock`) and `requires_industries`.
4. **Permissions**: list the industry roles in the registry; give them DocPerms in the DocType JSON.
   Create the roles in a `pre_model_sync` patch (DocType sync lists them) — see `patches/v0_4_0/create_industry_roles.py`,
   which already loops the registry.
5. **Workspace**: nothing to write — `sync.py` builds workspace, sidebar and desktop icon from `workspace_links`.
6. **API**: `api/v1/pharmacy/*.py` with `@frappe.whitelist()` + `@industry_api("pharmacy", roles)`.
7. **Tests**: copy the patterns in `tests/integration/test_industries.py` (2×2 permission matrix, 404 while off, switch
   persistence); registry integrity is checked by `tests/unit/test_industry_registry.py`.
8. **Enable** from ZG System Settings → Industries. After deploy run `bench --site X clear-cache` then `migrate`.

## Installation, migration, testing, deployment

- Fresh install: all industries off, no industry workspaces; the settings form lists every industry.
- Migrate re-applies `sync_industries()` (after_migrate); it is idempotent.
- Tests: `bench --site X set-config allow_tests true`, then
  `bench --site X run-tests --app zatgo_core` (industry tests: `--module zatgo_core.tests.integration.test_industries`).
- Deploy: follow `docs/deployment.md` and the workspace deploy rules (backup first, `docker cp` per container,
  `clear-cache` before `migrate`). Rollback = restore the pre-migrate backup and redeploy the previous commit;
  switching an industry off is the fast, data-preserving mitigation.

## Conventions

- Business logic in `industries/<key>/service.py`; API modules stay thin.
- Never create a DocType a standard one can satisfy; never touch GL / stock tables directly.
- A hook for an industry must return at once when it is off, and never return `None` from a permission hook.
- Public Workspaces created by code must not carry both `module` and `app` (Frappe's migrate deletes such
  workspaces that have no file on disk).
