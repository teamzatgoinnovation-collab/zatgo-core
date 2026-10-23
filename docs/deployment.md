# Deployment — ZatGo Core

1. Ship app sources to the bench `apps/` path (or install from this monorepo).
2. `bench migrate`
3. `bench build --app zatgo_core`
4. Restart workers / web: `bench restart`
5. Verify `/api/method/zatgo_core.api.v1.health.get_system_health`

## Production hardening

- Restrict Integration / Security settings to System Manager + Application Admin.
- Store provider secrets only in Password fields / vault — never commit.
- Enable audit (`ZG Security Settings.audit_enabled`).
- Monitor Redis and queue depth via System Health API / dashboard.

## The Hetzner box (2.29.17.8) -- how zatgo_core was shipped so far

*As last confirmed on 2026-10-21; check each fact before relying on it.* Only a runbook: nothing here is automated.

- The sites (accounting, democompanysa, kasibasia, testerp, ...) share ONE bench: the five `erpnext-*` containers
  (backend, queue-short, queue-long, scheduler, websocket) plus the frontend, from `/root/gitops/erpnext.yaml`
  (`-p erpnext`). `apps/zatgo_core` lives in each container's writable layer (not a volume), so the code is copied
  into **every** container; the frontend also needs `public/` (assets). The containers have no `git` access (no ssh).
- **Code is shared, data is not.** Copying new code in makes it live for every site on restart (JS/CSS assets at
  once); `bench --site X migrate` is per site. Safe order: code -> migrate **testerp** only -> test -> migrate the
  client sites. A change that acts without a migrate (permission hooks, API gates) is live everywhere as soon as
  the workers restart.
- Procedure that worked: (1) read-only: md5 the deployed tree against the commit you think is there; (2) stage a
  delta (`git archive <to> $(git diff --name-only <from> <to>)`, plus the list of files deleted) on the host
  (`/root/deploy-staging`); (3) back up the originals of the files it replaces and take a DB backup of each site you
  will migrate; (4) wait until `bench.log` has been quiet for ~3 minutes (other sessions deploy too); (5) per
  container: `docker cp` the tar to /tmp, `chown -R frappe:frappe` the app dir first (a root-owned file makes the
  extract fail half-way), extract as `-u frappe` into `/home/frappe/frappe-bench/apps/zatgo_core`; (6) frontend:
  copy `zatgo_core/public`; (7) gunicorn is PID 1 in the backend container: `kill -HUP 1`, then
  `docker compose -f /root/gitops/erpnext.yaml -p erpnext restart queue-short queue-long scheduler websocket`
  (there is no `pgrep` in the containers); (8) migrate testerp, verify via `information_schema` and read-only
  `bench execute` calls (do not create documents on a client's books), then the other sites one command each.
- Rollback = restore the backed-up files + HUP/restart; a migrated site's database is restored from its backup
  (patches are forward-only).
- Never recreate `erpnext-frontend-1` without immediately re-copying every custom app's `public/` into it.
- This app's changes since 0.4.0 need a migrate on each site: new Check `enable_vansalex` + patch `v0_4_7`,
  Warehouse field `zg_vansalex_transfer_point` + patch `v0_4_8`, VanSaleX Settings `max_adjust_qty`, indexes.
