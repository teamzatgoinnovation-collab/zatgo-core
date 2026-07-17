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
2. Read via `FeatureFlagService.is_enabled(...)` or Desk boot payload.
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

# lightweight unit tests (no site) where mocked
cd CustomApps/ZatGoCore && python -m pytest zatgo_core/tests/unit -q
```

## Regenerators

```bash
python3 CustomApps/ZatGoCore/scripts/generate_doctypes.py
python3 CustomApps/ZatGoCore/scripts/fix_controllers.py
python3 CustomApps/ZatGoCore/scripts/generate_reports.py
```

Prefer hand-editing controllers after generation.
