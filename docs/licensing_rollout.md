# Licensing rollout runbook (Phase 10)

How to take editions and licensing from the repository to the live sites **without locking anyone out**. Nothing
here has been run against the Hetzner server; every step marked *read-only* changes nothing, every other step is
yours to approve. Background and design: `licensing.md`; audit and decisions: `licensing_audit_2026-11-17.md`.

## 0. Where things stand (2026-11-25)

- **This repo, `main`**: phases 1-9 committed, plus the Phase 10 aids described below. Not pushed.
- **Not verified, needs a read-only look (step A):** another session reported (by message, not by anything this
  runbook could check) that its local branch `rename-zatgo` (`f3b62d4`, built on `6f102e9` = licensing phases 2-9
  as committed) was copied to the Hetzner containers and is migrating the sites. If so, licensing is already on
  the server **in its dormant state** (no signing key trusted, no site has the enforcement switch), and the server
  does **not** have this runbook's Phase 10 fixes (the Company cascade, the usage audit).
- **Names:** the rename drops the `ZG` prefix from DocTypes, including the licensing ones: `Licence`, `Licence
  History`, `Edition`, `Edition Feature`, `Module`, `Feature`, `Audit Log`. This runbook uses the new names (a
  site not migrated yet still has the `ZG ...` ones; patch `v0_6_0` renames them with their data). Page routes
  (`zg-licence`, `zg-edition-builder`) and `site_config` keys do not change.

## 1. What deploying changes on a site that has no licence

Dormant (nothing happens until a site has **both** the `zg_licence_enforcement` switch and an imported licence):
document gate, app / industry / VanSaleX gating, Desk menu filter, read-only expiry, limits.

Active the moment the code and a migrate land:

| Change | Effect |
|---|---|
| New DocTypes: Module, Feature, Edition (+ child), Licence, Licence History | tables created; Module / Feature filled from code (19 modules, 115 features); presets only on an issuer site |
| `Audit Log` is append-only | an insert **without** `ignore_permissions`, any update, and deleting a licensing entry are refused. Everything in this app writes it with `ignore_permissions`; a custom script of yours that inserts audit rows directly would now fail |
| Daily job `licensing.watch` | writes one `DefaultValue` row and audit entries when site_config licensing keys change |
| `licence` object in VanSaleX `me.context`, POS `pos_settings.get`, MyBis `get_context` | extra key; old app builds ignore it |
| `"*"` permission / document hooks | one config lookup per check |
| Licence page and Editions page in the ZatGo sidebar | visible to System Manager, ZatGo Application Admin, ZatGo Read Only |

## 2. Decisions that are yours

1. **Where the issuer runs.** Recommended: **not on the production server.** The signing key is the one secret
   that can mint licences; keep it on an offline or personal machine (the local dev bench already works as an
   issuer: `zg_licence_issuer: 1` and `zg_licence_issuer_key` in its site_config). Licences are files, so
   issuing off-box costs nothing.
2. **Generate the key** yourself, on that machine: `python3 scripts/licence_keygen.py /secure/path/key.pem`. It
   prints the one line for `zatgo_core/licensing/keys/public_keys.json`. Back the key file up somewhere safe: if
   it is lost, licences already issued keep working (only the public half is checked) but nothing new can be
   signed under that key id.
3. **Push** `main` (and decide how it meets `rename-zatgo`: that branch edits the same licensing files for the
   names, so merge it first or rebase Phase 10 onto it).
4. **Which edition each site gets** (step F decides this with data, not guesses).
5. **When enforcement is switched on, per site.**

## 3. Steps

### A. Look at the server first (read-only)
Do this before anything else; it replaces the guesses in section 0.

```bash
# from any release folder already on the server (the newest one in /root/deploy-staging); changes nothing
cd /root/deploy-staging/zatgo_core_<SHA> && ./deploy.sh check testerp.zatgoinnovation.com
# which sites exist, and for one site whether the licence tables are there (read-only SQL)
docker exec erpnext-backend-1 bash -lc "ls sites/"
docker exec erpnext-backend-1 bash -lc "bench --site testerp.zatgoinnovation.com mariadb -N -e \"select table_name from information_schema.tables where table_name in ('tabZG Licence','tabLicence')\""
docker exec erpnext-backend-1 bash -lc "grep -c 'zg_licence_enforcement\|zg_licence_issuer' sites/testerp.zatgoinnovation.com/site_config.json"
```

Per site, what you want to see: the licence tables exist (or not), `zg_licence_enforcement` and `zg_licence_issuer`
absent from `sites/<site>/site_config.json`, and the Tracker pages present
(`select name from tabPage where name like 'tracker%'`: a local site lost them after a migrate; a separate task is
investigating whether production is affected).

### B. Key and release
1. Generate the key (decision 2). Add the printed line to `licensing/keys/public_keys.json`, run
   `python3 -m unittest zatgo_core.tests.unit.test_licence_format` (the shipped-keys test checks the id), commit.
2. Push. Build the release with `deploy-staging/build_release.sh <FROM> <TO>` where `FROM` is the commit step A
   found on the server. The package contains every commit between the two, **including other sessions' work**
   (the ZatGo ERP Desk commits, the install changes): read the list `build_release.sh` prints before you copy it.

### C. Deploy to testerp first
`./deploy.sh plan`, `check testerp.zatgoinnovation.com`, `deploy`, `migrate testerp.zatgoinnovation.com`,
`verify testerp.zatgoinnovation.com`. Run the migrate from the queue-long container (`BACKEND=erpnext-queue-long-1`, detached, as learned on
2026-11-06) and tell any other session first: a backend restart kills a running migrate. Then, read-only:

- Licence page opens (`/desk/zg-licence`): "no licence imported", enforcement Off.
- Module / Feature counts: 19 and 115 (`select count(*) from \`tabModule\``; `tabZG Module` on a site not yet renamed).
- A Sales Invoice, a Payment Entry and a Stock Entry can still be created and submitted as before.
- Tracker pages present.

### D. Choose the edition with the usage audit (read-only)
On each site, before it gets a licence:

```bash
bench --site <site> execute zatgo_core.licensing.usage_audit.report --kwargs '{"edition_id": "sales"}'
```

It lists what the site created in the last 90 days that the edition would refuse. Anything in
`WOULD BE REFUSED` means the edition is too small: try the next one (`sales_inventory`, `distribution`, ...,
`enterprise`) until the list is empty, or build a custom edition on the issuer. A site you cannot size should
start on `enterprise`: it restricts nothing the registry describes, but still gives expiry, limits and the audit trail.

### E. Issue and import on testerp, then enforce
1. On the site: Licence page, menu, *Export site identity* (this creates the site ID). Send the file to the issuer.
2. On the issuer: Licence page, *Issue licence*, load the identity file, pick the edition, dates, limits. Keep the
   downloaded `.zglicence`.
3. On the site: *Import licence*. It must say Verified. Warnings show "imported but not enforced".
4. Only now, as the bench user, on that one site:
   `bench --site <site> set-config -p zg_licence_enforcement 1` then `bench --site <site> clear-cache`.
5. Use the site for a day: invoices, payments, stock, a return, a new company, the VanSaleX app. The Licence
   page's "Module access" must match what the customer bought.

**Undo, at any time, in seconds:** `bench --site <site> set-config -p zg_licence_enforcement 0` + `clear-cache`.
Nothing is deleted by enforcement; no data, document or ledger ever depends on it.

### F. The customer sites, one at a time
For each real site (accounting, democompanysa, kasibasia, ...): step D, then E with that site's own identity file
and licence. Order suggestion: democompanysa, accounting, kasibasia. The Space platform site (zatgoportal) is
outside this programme.

## 4. Rules for the rollout

- The private key never touches a server, a repository, a backup or a chat. Only `.zglicence` files and the
  public key travel.
- Never enable enforcement on a site whose licence has not verified on that site, or whose usage audit still lists
  refused documents.
- One site per step; wait a working day between customer sites.
- Imports, refusals, issuing and `site_config` changes are in `Audit Log` (filter by *Licence*).

## 5. Open items

- The VanSaleX app reads the licence block (`flutter-vansalex` commit `b56a6ab`, local, not pushed); POS, desktop
  accounting and MyBis apps do not yet.
- `scripts/licence_keygen.py` has only been run against a throwaway path; no real key exists.
- Delivery / fleet endpoints are not in the licensing registry (listed as exemptions in `api_coverage.py`).
- Reports and printing are never restricted by an edition (decision D6), so an edition that removes a module
  still lets its reports run.
