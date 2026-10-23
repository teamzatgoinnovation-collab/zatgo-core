# Developer Guide — ZatGo Core

## Consuming settings from another app

```python
from zatgo_core.services.settings_service import SettingsService
from zatgo_core.services.feature_flag_service import FeatureFlagService

system = SettingsService.get_system_settings()
company = SettingsService.get_company_settings("My Company")
if FeatureFlagService.is_enabled("zatgo.pos.split_payment", company="My Company"):
    ...
```

Prefer services over direct `frappe.get_single` so caching and permission guards stay consistent.

## Adding a feature flag

1. Create `ZG Feature Flag` row (`flag_key` like `zatgo.delivery.tracking`).
2. Read via `FeatureFlagService.is_enabled(...)` or boot payload / client API.
3. Never hardcode enablement in product apps.

## Adding a number series

Edit **ZG Number Series Settings** child table, or seed in a patch under
`zatgo_core/patches/`.

## Extending settings

1. Add fields to the relevant DocType JSON.
2. Add validation in `zatgo_core/validation/`.
3. Expose through `SettingsService` / API if clients need it.
4. Update docs + tests.

## Coding standards

- Type hints on public functions
- PEP8
- Docstrings on modules/classes/public methods
- No duplicated settings logic outside services
- No hardcoded DocType names — use `zatgo_core.constants.DOCTYPES`

## Tests

```bash
# from bench
bench --site <site> run-tests --app zatgo_core

# one module
bench --site <site> run-tests --app zatgo_core --module zatgo_core.tests.integration.test_app_switches

# unit tests that need no site (naming standard, parts of the catalog): from the repo root
python3 -m unittest zatgo_core.tests.unit.test_naming_standard
```

`allow_tests` must be set on the site (`bench --site <site> set-config allow_tests true`). Many integration tests
need a seeded company/warehouse and skip themselves on an empty site — run them on a seeded one.

## Regenerators — do not run

`scripts/generate_doctypes.py`, `fix_controllers.py` and `generate_reports.py` were the first scaffold. Their
templates are stale: running them **overwrites hand-edited controllers and DocType JSON** (for instance
`zg_system_settings.py` would shrink to a stub). They now refuse to run without `--i-know-this-overwrites`.
Edit DocType JSON and controllers directly.

## Adding an app

See `plugin_guide.md` (the app contract) and `naming.md`. In short: a manifest, a switch, a gate; every app
and its settings then show up in **ZatGo Apps**, the sidebar and the registry without further edits.
