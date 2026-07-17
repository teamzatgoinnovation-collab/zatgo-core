# Upgrade Guide — ZatGo Core

## Standard upgrade

```bash
# update app sources
bench --site <site> migrate
bench build --app zatgo_core
bench --site <site> clear-cache
```

`after_migrate` and patch `v0_1_0.seed_core_defaults` re-assert:

- roles
- singleton settings
- default number series (only if empty)
- default feature flags (only if missing)

## Compatibility

- App registry stores `minimum_version` / `maximum_version` per registered app.
- Dependent apps should validate against registry before enabling features.

## Breaking-change policy

1. Never rename DocTypes without a patch + ADR.
2. Prefer additive fields.
3. Password/secret fields must remain `Password` type.
4. Document API removals in `docs/CHANGELOG.md`.

## Rollback

1. Restore MariaDB backup.
2. Re-checkout previous `zatgo_core` tag.
3. `bench migrate` (forward-only patches — restore DB for true rollback).
