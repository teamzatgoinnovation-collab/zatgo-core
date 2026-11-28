# Release runbook — ZatGo Core

*Phase 15, 2026-11-28. Release 1.0.0.* Deployment mechanics for the Hetzner box are in `deployment.md`; general
upgrade notes in `upgrade.md`. This page is the checklist a release goes through.

## Versioning
Semantic versioning, one number in four places (`zatgo_core/__init__.py`, `hooks.app_version`, `pyproject.toml`,
`setup.py`), checked by `tests/unit/test_release_identity.py`. A release is a git tag `vX.Y.Z` on `main`; a deploy
is always a full tree from a tag, never a working copy.

- **Major**: a change a client app or a site admin must act on (endpoint removed, DocType renamed, a POST-only
  switch for an endpoint a client still calls with GET).
- **Minor**: new features, new settings, patches that only add.
- **Patch**: fixes with no migration.

## Compatibility matrix (1.0.0)
| Component | Supported |
|---|---|
| Frappe | 16.x (tested 16.29) — `before_install` refuses other majors |
| ERPNext | 16.x (tested 16.31) |
| Python | 3.11+ |
| MariaDB | 10.6+ (production 11.8; concurrent same-series inserts can return error 1020, retried) |
| ZatGo clients | flutter-vansalex, zatgo-vansalex-native, desktop-accounting, web-accounting, zatgo-pos, mybis: all POST their writes (required since 1.0.0) |

## Before a release
1. Full local suite on the bench; compare with the last baseline (`scratchpad/summ.py`-style summary). No new
   failure without an explanation in the release notes.
2. `git diff <last tag>..main --stat`; every patch in `patches.txt` exists and is in the right section
   (`[post_model_sync]` when it needs new columns).
3. `CHANGELOG.md` has the version, what a site admin must do, and what a client must change.
4. Tag `vX.Y.Z` and push the tag with `main`.

## Deploy (per server)
1. Read-only check: md5 the deployed tree against the commit it should be (other sessions deploy too).
2. Backup each site you will migrate: `bench --site <site> backup --with-files`.
3. Copy the tagged tree into every container (`deployment.md`); restart workers; frontend gets `public/`.
4. Migrate **testerp** first, from `queue-long` (not backend), detached.
5. Smoke test on testerp: Sales Invoice, Purchase Invoice, Payment Entry, Journal Entry, Stock Entry — create,
   submit, check GL and stock ledger, cancel. Check `information_schema` for any new column or index.
6. Only then migrate the client sites, one at a time, each with its own backup and health check
   (Error Log, a Desk page load, one API call per client app).

## Migration checklist (per site)
- Backup taken and its size looks right.
- `bench --site X migrate` exit code 0; no new Error Log rows during it.
- New schema present (`information_schema.COLUMNS` / `STATISTICS`), not just "patch recorded".
- `bench --site X clear-cache` (hooks and permission caches).
- Desk loads; Module Settings and the ZatGo Settings workspace open.

## Rollback
- Code: restore the backed-up app tree (or copy the previous tag), `kill -HUP 1` in backend, restart workers.
- Data: patches are forward-only. A migrated site goes back only by restoring its backup:
  `bench --site X restore <sql.gz> --with-public-files ... --with-private-files ...`.
- Decide within the first hour: a restore loses everything posted since the backup.

## Release 1.0.0 — site admin actions
- Mark a default Sales (and, if used, Purchase) Taxes and Charges Template per company: accounting-API invoices
  now carry it (T-01).
- Give users Role Profiles (personas) and User Permissions as needed (`permissions.md`).
- Review Module Settings: switch off modules the site does not use.
