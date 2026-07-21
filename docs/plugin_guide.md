# Plugin Author Guide — ZatGo Core

ZatGo Core never hardcodes product menus. Applications register a **manifest**;
Core persists it as `ZG Registered Application` + `ZG Setting Section` rows.
Clients and future domain Desk UIs consume these via `zatgo_core.api.v1.config.*`.

## Manifest shape

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

Or via API (Application Admin):

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
