# Migration plan

*Phase 4, 2026-11-28. How sites move from the `ZG` names (`main-zg-legacy`, last deployed `1a0e621`) to the current `main` (no prefix, ADR-005) without losing data.*

## What the migration does
`[pre_model_sync]` patch `v0_6_0/rename_zg_to_zatgo` runs first on `bench migrate`:
- `frappe.rename_doc` on **59 DocTypes**. That renames the table, and repoints Link fields, child tables, DocPerms, Custom DocPerms, Custom Fields and Property Setters.
- Renames 8 Number Cards, the Roles and the "ZG ERP Summary" block to `ZatGo …`.
- It is idempotent: a name already renamed, or never present, is skipped. When both the old and new names exist, it leaves the old one and reports it. It never merges or deletes.
- Model sync then sees the new DocType JSON and finds the renamed tables in place.

Tested on a local `vansale1` upgrade (271 trips, 63 orders kept, roles renamed; commit `f3b62d4`) and on `zg-accounting-test.localhost` (2026-11-28, Phase 3 baseline).

## What must move with it
Anything that names a DocType moves in the same release: hooks keys, raw SQL table names, workspace and sidebar JSON, JS routes, client apps that call `frappe.client` with DocType names, and print formats. The no-`ZG` line already carries these. **Client apps** (VanSaleX, POS, MyBis, desktop/web accounting) call `zatgo_core.api.v1.*` methods, whose paths are unchanged. **They have not been checked for direct DocType-name use** — check each before the first client site migrates.

The **uncommitted work in the old checkout** (40 files on `main-zg-legacy`) is written with `ZG` names. Its owners port it to `main` before it ships.

## Rehearsal (before any client site)
For each of accounting, democompanysa, kasibasia (testerp first):
1. Copy the site's database backup (taken by `deploy.sh migrate` or `bench backup`) into a throwaway local site: `bench --site rehearse-<site>.localhost restore <backup>`.
2. Run `data_integrity.report` on it and keep the output (before).
3. Count rows per renamed table:
   ```sql
   SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE 'tabZG %';
   ```
4. Put the rehearsal site on `main` and run `bench --site rehearse-… migrate`. Watch for `v0_6_0` reporting a "both exist" conflict.
5. Run `data_integrity.report` again (after). Row counts of the renamed tables must equal step 3; no new dangling links or duplicates; `deploy_check` ok.
6. Open the site in a browser: ZatGo folder, each app's sidebar, a Sales Invoice print, a VanSaleX login, a POS sale.
7. Run the money-path suite against the rehearsal site.

## Live migration (needs explicit approval; see `feedback_reengineering_autonomy`)
1. Deploy the `main` tree from a tag to the five containers. The code is live for every site the moment it lands, and sites not yet migrated still have `ZG` tables. **So deploy, then migrate every client site in the same window**, testerp first.
2. `deploy.sh migrate <site>`: takes a backup first, migrates, then runs `deploy_check`. Run it from `erpnext-queue-long-1`, and tell other sessions not to restart containers.
3. `data_integrity.report` per site, compared with the rehearsal.

## Rollback
- **Code**: `deploy.sh rollback` restores the previous tree. A site already migrated keeps its renamed tables, and the old code cannot read them. **So a rollback after a migrate means a database restore** from the backup step 2 took, then the old code.
- **Never** rename tables back by hand.

## Later migrations (planned)
| Change | Phase | Approach |
|---|---|---|
| `Module Settings` replaces the `enable_*` switches | 5 | a patch copies each switch into its row; `app_state` reads the rows with a fallback for one release; the old fields stay (hidden) until a later release |
| Legacy names (VanSaleX *, AI *, Tracker *, Space *) | not planned | keep (ADR-005) |
| `track_changes` on AI Scheduled Task | 12 | DocType JSON change, no data move |
