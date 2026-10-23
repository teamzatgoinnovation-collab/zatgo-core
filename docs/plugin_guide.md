# Plugin Author Guide — ZatGo Core

ZatGo Core never hardcodes product menus. Applications register a **manifest**;
Core persists it as `ZG Registered Application` + `ZG Setting Section` rows.
Clients and future domain Desk UIs consume these via `zatgo_core.api.v1.config.*`.

## The app contract (apps shipped inside zatgo_core)

An app is one manifest. It appears in **ZatGo Apps** (`/desk/zg-app-hub`), the generated ZatGo sidebar, the
switch fields, the API gate and the registry with no other list to edit.

```python
# <module>/app_manifest.py   (module folder)   or an entry in plugins/manifests/core_apps.py
APP = {
    "key": "my_app",                     # unique, snake_case            (required)
    "label": "ZatGo My App",             # "ZatGo ..." prefix            (required)
    "group": "bundled",                  # app | bundled | ui | core | industries   (required)
    "icon": "project", "description": "What it does.",
    "switch_field": "enable_my_app",     # default for bundled = enable_<key>; no switch = always on
    "default_on": False,                 # True only for an app that was always on before it got a switch
    "module_def": "My App",              # bundled only
    "workspaces": ("ZatGo My App",),     # the first that exists is its "Overview" in the sidebar
    "settings": (("My App Settings", "My App Settings"),),
    "version": "1.0.0",                  # default: zatgo_core's
    "requires": ("vansalex",),           # these must be on to switch this one on
    "api_prefixes": ("zatgo_core.api.v1.my_app.",),   # end with "."; 404 while off
}
```

New **bundled module** (own DocTypes):

1. `zatgo_core/<module>/` with `app_manifest.py`, `install.py::bootstrap()` (roles, settings, Desk records) and
   `desk_records/` (workspace + sidebar JSON, deliberately outside Frappe's synced folders); add the Module Def
   name to `modules.txt`. Its `enable_<key>` field is created on migrate.
2. Every hook it needs goes through a wrapper in `services/bundled_apps.py` that returns at once when the app
   is off (and `hooks.py`).
3. Its whitelisted methods live under `zatgo_core.<module>.` — gated automatically; add `@app_api("my_app")`
   (services/app_gate.py) where a function must also require a login or roles.
4. DocTypes are named `ZG <Name>` (`naming.md`).
5. Deploy: `bench clear-cache` **before** `migrate` (a new module in `modules.txt`).

New **in-core app** (group `app`, like VanSaleX): a manifest entry with `api_prefixes` and a `switch_field`; if it
existed before it had a switch, set `default_on` **and** ship a patch that stores 1 (the form would otherwise
open unticked and a save would switch it off — see `patches/v0_4_7`). Its workspace stays a synced file and is
hidden, not deleted, while the app is off (`services/app_desk.py`).

`tests/integration/test_app_hub.py` fails if a module with DocTypes has no manifest;
`tests/unit/test_naming_standard.py` fails on a new DocType without the `ZG ` prefix.

## Registry vs catalog

The plugin registry below is what config-center *clients* read (`zatgo_core.api.v1.config.*`). For the apps
the catalog owns it is **generated** (`plugins/discover.py`, on migrate and whenever a switch changes) with
the real enabled state and version — do not hand-write a manifest for them. Hand-written manifests are for
apps the catalog does not know (POS, Delivery, Kitchen); VanSaleX keeps its hand-written *sections* but takes
its title, version and enabled state from the catalog.

## Manifest shape (registry — hand-written manifests and external apps)

```python
MANIFEST = {
    "app_key": "my_app",          # unique snake_case
    "title": "My App",
    "version": "1.0.0",
    "icon": "folder",
    "category": "Operations",     # Operations|Sales|Inventory|HR|Finance|Platform|Other
    "menu_order": 50,
    "enabled": 1,
    "visible": 1,
    "roles": "System Manager,ZG Application Admin",  # empty = all
    "depends_on": "zatgo_pos",    # optional comma-separated app_keys
    "description": "…",
    "settings_route": "",         # optional; domain app Desk route if any
    "sections": [
        {
            "section_key": "general",
            "label": "General",
            "sort_order": 10,
            "link_doctype": "ZG System Settings",  # OR
            # "component": "module_preferences" | "about" | "pending",
            # "defaults_json": {...},
            # "roles": "…",  # optional override
        },
    ],
}
```

## Register from your app

In your product app’s `after_install` / `after_migrate`:

```python
from zatgo_core.services.plugin_registry_service import PluginRegistryService

PluginRegistryService.register_application(MANIFEST, ignore_permissions=True)
```

Or via API (System Manager / Application Admin):

```text
zatgo_core.api.v1.config.register_application
```

## Section host types

| Host | Behaviour |
|------|-----------|
| `link_doctype` | Points at a DocType (Single or List) for clients / operators |
| `component=module_preferences` | Toggle grid; saved via `update_settings` |
| `component=about` | Read-only app meta |
| `component=pending` | Placeholder until domain UI exists |

## Visibility

Users only see applications/sections whose `roles` intersect their roles.
System Manager and ZG Application Admin see everything.

## Bundled Phase-1 samples

Shipped under `zatgo_core/plugins/manifests/`:

- `zatgo_pos`
- `delivery`
- `kitchen`

Re-seed:

```bash
bench --site <site> execute zatgo_core.plugins.discover.discover_and_register_manifests
```
