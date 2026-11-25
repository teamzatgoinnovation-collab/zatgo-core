# Editions and licensing

Status: **Phase 10 of 10 — rollout prepared, not executed.** The code is complete and tested; going live needs
the real signing key, a push and your approval of each deploy step: see `licensing_rollout.md`. A site enforces
its licence only when its `site_config` has `zg_licence_enforcement` and a licence is imported; no production site
is known to have either. Audit and decisions: `licensing_audit_2026-11-17.md`.

## Decisions (product owner, 2026-11-17 — the audit's recommended defaults)

| # | Decision |
|---|---|
| D1 | On a customer site only the **signed licence** is trusted. Editions are written where the issuer runs, never on a customer site. |
| D2 | The issuer is a mode of zatgo_core on one internal, non-public ZatGo site. The private key is a file outside `sites/` (never in a site DB or backup). |
| D3 | Space subscription and licence combine as **most restrictive wins**; a missing input restricts nothing. |
| D4 | A site with no licence stays **unrestricted** until enforcement is switched on for it (a site_config key only the bench user can write). |
| D5 | A licence binds to a site UUID in `site_config.json` plus the site name; multi-site only when the licence lists the sites. |
| D6 | Downgrade: features no longer licensed become read-only. Cancelling an existing document is allowed; amending is refused. |
| D7 | Gate Management and GST/India are not registered (nothing implements them). |
| D8 | Order: Sales, Accounting, Inventory, POS, Enterprise. HR / CRM / Production are registered but not tuned. |
| D9 | Licensed users = enabled System Users, not Administrator, not API-only users. |
| D10 | An exceeded limit blocks creating more; existing users are never disabled. |

## The registry (`zatgo_core/licensing/`)

- `registry.py` — the model and the rules; pure Python (no database), like `services/app_catalog.py`.
- `catalog/*.py` — one file per module (or a few small modules per file, `MODULES = [...]`).
- `catalog/ids.lock` — every feature id ever shipped.
- `sync.py` — projects the registry into `Module` / `Feature` on install and migrate.

**Module** — commercial grouping (Sales, Inventory, ...). **Feature** — what an edition includes and a licence
signs. A feature carries:

| key | meaning |
|---|---|
| `id` | `<module>.<feature>`, lower snake case, **stable forever** |
| `doctypes` | `dt(DocType, actions, **match)` grants; `match` narrows to documents whose fields equal the values (`is_return=1`, `purpose="Material Transfer"`, or a tuple of values) |
| `reports`, `pages`, `workspaces` | names of existing records it covers |
| `api_prefixes` | zatgo_core whitelisted-method prefixes (module path + `.`) that belong to it |
| `requires` | `{feature_id: [actions]}` needed beyond the foundation (`[]` = the feature as a whole) |
| `platforms` | `desk`, `desktop`, `mobile` |
| `source_app` | app that implements it; the feature is unavailable on a site without it |
| `app_key` / `industry` / `vansalex_keys` | bridge to `services/app_catalog.py`, `industries/registry.py`, `services/vansalex_access.py` — those stay the truth for switches and VanSaleX settings |
| `foundation` | part of every edition (setup, masters read-only, users, backups) |
| `retired` | the only way an id leaves the product |

Actions: `read create write delete submit cancel amend print email export import report share`. Bundles:
`VIEW`, `READ_ONLY`, `MASTER`, `TRANSACTION`, `SETTINGS`.

Rules (`tests/unit/test_licensing_registry.py`):
1. **Never rename or delete an id** — a signed licence names it. Retire it, and keep its line in `ids.lock`.
2. **`NEVER_GATE`** DocTypes are never mapped: GL / payment / stock ledgers, Bin, reposting, Serial and Batch
   Bundle, ZATCA records made on submit, system and log records. Gating them would stop a Sales Invoice from
   posting. Read access to them stays with role permissions alone.
3. **No child tables** — they follow their parent (integration test).
4. **Dependencies are reported, never added**: `registry.resolve_requirements(ids)` lists what is missing and
   which module it belongs to; it never switches a paid module on.
5. A DocType can sit in several features (Account: read in `foundation.masters_read`, full in
   `accounting.chart_of_accounts`). Phase 4 grants the union over the licensed features.

Totals at this commit: 19 modules, 115 features, 148 DocTypes mapped.

### What is deliberately not a feature
Cash Book / Bank Book (ERPNext has none — the General Ledger on a cash or bank account is that book), "Apply
discount" (a field, covered by VanSaleX keys and Phase 4 field rules if wanted), Gate Management and GST (D7),
the print view itself (printing is each DocType's `print` action), the ZATCA Phase 1 QR on invoices (legal on
every KSA invoice).

## The projection: `Module`, `Feature`

Read-only DocTypes (core module) for the Desk and for Phase 3's edition builder to link to. Read for System
Manager, ZatGo Application Admin, ZatGo Read Only; nobody can create, change or delete a row — the controller refuses
any write outside the sync, `ignore_permissions` included. `sync_registry()` (from `install.after_migrate` and
`after_install`) writes a row only when the code changed, so a re-run writes nothing; a feature that left the
code is marked retired, never deleted. `available` = its source app is installed on this site.

## Adding a feature

1. Add it to the module's file in `catalog/` (`feature(...)`, real DocTypes / reports only).
2. Add its id to `catalog/ids.lock`.
3. Run `tests/unit/test_licensing_registry.py` (structure) and `tests/integration/test_licensing_registry.py`
   (everything it names exists on the site).

## Editions (Phase 3)

An **edition** is a commercial product configuration (`Edition` + child `Edition Feature`): which
registry features it includes — each optionally narrowed to fewer actions — on which platforms (Desk, desktop
apps, mobile apps), with which licence defaults (type, duration, trial days, maximum users / companies, 0 = no
limit) and suggested default roles. Foundation features are in every edition and are never listed.

It is a **template**. A licence (Phase 5) will carry its own signed copy of the resolved features, so changing
an edition never changes a licence that was already issued.

### Issuer mode (decision D2)
Editions are written only on the licence issuer site: `"zg_licence_issuer": 1` in its `site_config.json`
(`licensing/issuer.py`), and only by a System Manager. The `Edition` controller enforces it, so the form, REST
and the builder page are all bound; on every other site editions are read-only. The private signing key
(Phase 5) will also live only there, outside `sites/`.

### Rules (`zg_edition.py`, `licensing/edition_config.py`)
- Features must be live registry features, not foundation ones; narrowed actions must be ones the feature grants.
- **Active** = no missing dependency. A Draft may miss some (its `Dependencies` tab lists them); nothing is ever
  added for it.
- The **version** goes up whenever what the edition grants changes (features, actions, platforms, licence
  defaults, default roles — `grant_hash`); renaming or a status change does not bump it.
- **Archived** editions cannot change until set back to Draft. Only a **Draft** can be deleted.
- Field changes and feature-table changes go to `Audit Log` (derived fields are left out).

### Presets (`licensing/editions/*.json`)
Sales, Accounting, Inventory, POS, Sales + Inventory, Accounting + Inventory, Retail, Distribution, Enterprise
(`"features": "*"` = every live feature) and an empty Custom Edition (Draft). Each is checked by the unit tests
to have no missing dependency. On the issuer site `after_migrate` creates any preset that does not exist yet and
never touches one that does (`editions.seed_presets`).

### Dependency Inspector (`licensing/inspector.py`)
For any selection (saved or not): missing dependencies with the module each belongs to; every DocType with its
actions and field conditions, reports, pages, workspaces and API prefixes (foundation included); the Single
settings users can change; and **what submitting writes** — for each transaction DocType the edition may
submit, the ledgers ERPNext posts itself (GL Entry, Payment Ledger Entry, Stock Ledger Entry, ZATCA records
when `tax.zatca` is in) and the reposting jobs (`repost_entries`, `run_parallel_reposting`). Those ledgers are
never gated; they are listed so a reader sees what a Sales-only edition still writes. Also warns about
features this site cannot run (app not installed) and features no edition platform reaches.

### Edition files (export / import)
`{"type": "zatgo.edition", "schema_version": 1, "product_id": "zatgo_erp", ...}` plus an informational
`resolved` block (modules, dependencies, DocType / report / workspace mappings — recomputed on import, never
trusted). Import is previewed first (create / update / unchanged / refuse, a diff against the existing edition,
the inspection); replacing an existing, different edition needs an explicit overwrite; an Active file with
missing dependencies comes in as a Draft; a licence file (`zatgo.licence`) or a newer schema is refused. Every
import is recorded in `Audit Log` (`fieldname = import`, file hash).

### The page: **ZatGo Editions** (`/desk/zg-edition-builder`)
System Manager, ZatGo Application Admin, ZatGo Read Only may open it; only a System Manager on the issuer site can
change anything (elsewhere it says so and is read-only). Left: editions by status. Middle: modules with feature
checkboxes, search, per-feature action narrowing, availability and `requires` tags. Right: live summary,
platforms, licence defaults, warnings with an **Add** button per missing feature (an explicit choice). Menu:
New, Import, Duplicate, Archive / Restore, Compare, Export; **Dependency inspector** opens the full report.
There is no "Activate on site" yet: that needs a signed licence (Phases 5-6).

API: `zatgo_core.api.v1.licensing.editions.*` (`get_builder`, `get_edition`, `inspect`, `save_edition`,
`duplicate_edition`, `set_edition_status`, `compare_editions`, `export_edition`, `preview_import`,
`import_edition`, `import_history`); writes are POST only and go through the controller.

## Enforcement (Phase 4)

### When it is on (`licensing/entitlement.py`)
Only when **both** hold: `"zg_licence_enforcement": 1` in the site's `site_config.json` (bench-owned, D4) and
an **entitlement** exists — the licensed features with their actions, foundation always included. Otherwise
everything is unrestricted (fail-open). Phase 4 has no entitlement source on any site; Phase 5's verified
licence plugs into `entitlement._load()`. `entitlement.use(...)` installs one per request (Python only: the
loader and the tests).

### What is refused (`licensing/gate.py`, decision D6)
| Action | Unlicensed |
|---|---|
| create, write, delete, submit, amend, import | **refused** |
| read, print, email, export, report, share | allowed — history stays viewable and printable (ZATCA) |
| cancel | allowed — mistakes stay reversible through ERPNext's own cancellation |

A check is decided per **document**: the registry grants that match it (`is_return`, Stock Entry `purpose`, ...)
and whether a licensed feature gives the action. DocTypes the registry does not map (ledgers, NEVER_GATE, anything
not product-controlled) and documents no feature describes (a Stock Entry purpose nobody lists, e.g. Repack)
are never touched. The message names the feature that would allow it.

Layers, as in `subscription_gate`: `has_permission "*"` (Desk buttons, REST, list actions; Frappe skips it for
Administrator) and `doc_events "*"` — `validate` (after the controller's own, so `purpose` is set; create /
amend / write / submit by `_action`), `on_trash`, `before_update_after_submit` — which catches
`ignore_permissions`, Administrator in a request, imports and jobs a user started. Exempt: install / migrate /
patch, and Administrator outside a request (scheduler, bench console).

### Apps, industries, VanSaleX
An app (`app_key`), industry or VanSaleX key that some feature names is **off when the licence does not include
it**, whatever its switch says: `app_state.is_on` / `switches()`, `industries.gate.enabled_keys` and
`vansalex_access.effective` ask `licensing.gate`, so the existing API 404s, sidebars, hub and `me.context.access`
follow. Switching such an app or industry **on** is refused by `app_authority` (switching off always works).

### Desk (`licensing/desk.py`)
At the end of `boot_session`, workspaces, sidebars, rail icons and pages that only unlicensed features list are
left out of the boot payload — per request, nothing stored, so a new licence shows them again at the next load.
Navigation only: the gate is what refuses, and a direct URL still opens a record read-only.

### Cross-feature effects in `requires`
Documents one feature's flow makes for another are declared so editions include both: POS Invoice → Sales
Invoice (closing entry consolidation), Payroll Entry → Journal Entry, VanSaleX cash invoice → Payment Entry.

### Known gaps (by design of Frappe, as in `subscription_gate`)
Writes through raw SQL / `db.set_value` / `db_set` fire no document event; a job Administrator enqueued from a
request runs without one. Narrowing an edition's *viewing* actions (print, export, report) is recorded but not
enforced (D6).

## Licences (Phase 5)

### The file (`licensing/licence_format.py`)
`<number>.zglicence`: `{"type": "zatgo.licence", "format": 1, "key_id", "payload": base64, "signature":
base64}`. The Ed25519 signature covers the exact payload bytes, and those bytes must be the canonical JSON of
what they decode to (sorted keys, compact, UTF-8, no floats). Payload: licence id (UUID), number, version,
product `zatgo_erp`, customer, site ids (+ optional site names), edition id / name / version, **resolved
features with their actions** (taken from the edition at issue time — later edition changes never touch it),
licence type, issue / start / expiry dates (no expiry for Lifetime / Perpetual), grace days, platforms, limits
(users / companies / sites, 0 = none), device policy, issued_at, key id. A revocation list is the same envelope
(`zatgo.revocation`) around `{"revoked": [licence ids]}`; an edition file is refused as a licence and vice versa.

### Keys (`licensing/crypto.py`, `scripts/licence_keygen.py`)
- Sites trust only public keys shipped in code: `licensing/keys/public_keys.json` (key id = first 16 hex of
  SHA-256 of the raw key). Nothing on a site can add one. **It is empty today**: no licence can be imported
  anywhere until a real key is generated and its public half committed.
- Generate the key **on the issuer host**: `python3 scripts/licence_keygen.py /secure/path/key.pem` (mode 600,
  never overwrites). It prints the `public_keys.json` line to commit and the issuer site's
  `"zg_licence_issuer_key": "<path>"`. The private key must stay outside the bench's `sites/` folder (backups)
  and owner-readable only — signing refuses otherwise — and never enters a site database, a repository or a
  licence file. Rotation = add a new key id; a leaked key = remove its public key and re-issue.

### Issuing (issuer site, `licensing/issuing.py`)
`issue(edition_id, customer_name, site_ids, ...)` — Active, dependency-complete editions only; dates and limits
default from the edition's licence defaults; `replaces=<licence id>` issues the next version of an existing
licence. The signed file is recorded in **Licence History** (number series `ZGL-.YYYY.-.#####`) and audited.
`revocation_list([licence ids])` signs a revocation list. API: `zatgo_core.api.v1.licensing.licences.
issue_licence / issued_licences / revoke_licences` (POST for writes; issuer + System Manager).

### Importing (customer site, `licensing/licences.py`)
`import_licence(file)`: signature with a trusted key → schema / product / dates / features → **site binding**
(this site's `zg_site_id` from `site_config`, created the first time the identity is read — never on migrate —
plus the site name when the licence lists names) → refuse a licence not started yet, expired, revoked, already
imported, or older than the version in force → store the original signed file in **Licence** (it becomes
current) → audit. Refusals are audited with a reason code. `import_revocation(file)` marks listed licences
Revoked. API: `site_identity_info` (the IDs to send to the issuer), `current_licence`, `import_licence`,
`import_revocation`, `verify_licence` — System Manager for everything but reading.

### What the site trusts
Only the signed file. The entitlement (`entitlement._load` → `licences.current_entitlement`) is rebuilt from
the stored file — signature and site re-checked — and cached for an hour or until the next import / revocation.
A record edited in the database no longer verifies and gives the **foundation only**; so does a revoked
licence. `Licence` and `Licence History` cannot be written by hand (controller), and `Licence` stays
writable on a read-only (lapsed subscription) site so a licence can reactivate it.

### Offline limits (stated, not hidden)
- Binding is tamper-evident, not tamper-proof: someone with shell access can copy `zg_site_id` and the site name.
- There is no central revocation: a signed revocation list or a replacement licence is imported like a licence.
- The clock is the server's: Phase 7's rollback check is best effort (see below).

## The Licence page (Phase 6): **ZatGo Licence** (`/desk/zg-licence`)

In the ZatGo sidebar under General Settings, next to **Editions** (both are shortcuts of
`workspace/zatgo/zatgo.json`). Readers of Licence (System Manager, ZatGo Application Admin, ZatGo Read Only) see it;
every action is a System Manager's, enforced on the server.

- **Overview**: edition, status, customer, licence number and version, type, issue / start / import / expiry
  dates, days remaining, signature verified or not, feature count; **this site**: site name and ID, ZatGo
  version, users and companies against the licence limits (D9: enabled System Users other than Administrator;
  Company records), whether enforcement is on.
- **Warnings** (`licence_overview.warnings`): no trusted signing key yet; no licence (danger when the switch is
  on); licence no longer verifies; revoked; expired; trial ending (7 days); expiring (30 days); users / companies
  over the limit; imported but not enforced.
- **Module access**: every module with licensed / total features and, per feature, the actions it gets. With no
  licence it says *unrestricted*; a revoked or broken licence shows only the foundation.
- **Activation history**: every imported licence (current one marked, download its signed file) and the licence
  events of Audit Log (imported, rejected with reason, revoked, verification failed).
- **Actions** (menu): Import / Replace licence, Verify licence, Import revocation list, Export site identity
  (`zatgo.site_request` — the file to send ZatGo for a licence; creates the site ID the first time), Export
  licence information (`zatgo.licence_info`, a metadata backup — never importable), Download licence file.
- **Issuer section** (issuer site + System Manager only): Issue licence (Active editions; customer; site IDs —
  or load the customer's site identity file; type, dates and limits, blank = the edition's defaults) which
  downloads the signed file; every issued licence with Download, Replace (next version) and Revoke (downloads a
  signed revocation list).

API: `zatgo_core.api.v1.licensing.licences.get_page / site_request / licence_info / download_licence /
download_issued`, plus the Phase 5 endpoints. Data: `licensing/licence_overview.py`.

## Expiry, grace, clock and limits (Phase 7, `licensing/licence_policy.py`)

All of this applies only while the enforcement switch is on.

| Situation | Effect |
|---|---|
| no licence, an invalid one, or a revoked one | **foundation only** (the basics can be changed, nothing else) — deleting the licence record never lifts a restriction |
| up to the expiry date | normal; the page warns 30 days ahead (a trial 7) |
| after expiry, within `grace_days` | normal, with a danger warning naming the read-only date |
| after the grace | **read-only site** |
| server clock more than the tolerance behind the highest time seen | **read-only site** until the clock is corrected |
| Lifetime / Perpetual | never expires |

**Read-only** is the same gate a lapsed Space subscription uses (`services/subscription_gate.py`): `current()`
merges the licence verdict, the most restrictive wins (D3). Viewing, reports, printing, exports, backups and
importing a new licence (Licence is exempt) keep working; every create / update / delete / submit / cancel /
amend is refused with a licence message, and the Desk badge says why. Nothing is deleted.

**Clock**: the highest time seen is stored in the `DefaultValue` row `zg_licence_clock_hwm`, moved forward at most
hourly and written directly (no document events, no cache clear — a normal save would run the read-only gate
again). Tolerance: `site_config` `zg_licence_clock_tolerance_hours` (default 48). Someone with database access can
reset it: best effort, as the brief requires.

**Limits** (D9 / D10, in `licensing/gate.py::check_limits`): a new licensed user — an enabled System User other
than Administrator, i.e. one with a desk role — or enabling one, is refused once `max_users` would be exceeded; a
new Company once `max_companies` would be. Editing existing users and companies is never refused and nothing is
disabled. Scheduler / console work (Administrator outside a request) is exempt.

## Client contract (Phase 8, `licensing/capabilities.py`)

For ZatGo's own clients (VanSaleX mobile / web, ZatGo POS and the desktop accounting apps, MyBis), with the same
stable ids as the registry and the licence. A **hint** for what to show — the server enforces every rule whatever
a client hides; a hidden mobile feature is not a secure one.

**Full contract**: `GET zatgo_core.api.v1.licensing.capabilities.get?platform=desk|desktop|mobile` (any logged-in
user):

```json
{"schema_version": 1, "product_id": "zatgo_erp", "digest": "16 hex, changes when anything below changes",
 "licence": {"enforced": true, "licensed": true, "read_only": false, "read_only_reason": null, "message": null,
             "edition_id": "sales", "edition_name": "ZatGo Sales", "status": "Active", "expiry_date": "2027-11-23",
             "days_remaining": 364},
 "platforms": {"desk": 1, "desktop": 1, "mobile": 0}, "platform": "mobile", "platform_allowed": false,
 "modules": {"sales": true, "inventory": false},
 "features": {"sales.invoice": {"licensed": true, "actions": ["read", "create", "submit"]},
              "inventory.stock_transfer": {"licensed": false, "actions": []}},
 "apps": {"vansalex": false, "zatgo_pos": true}, "industries": [],
 "user": {"name": "user@example.com", "roles": ["Sales User"]}}
```

`licensed: null` / `modules: null` = the site enforces no licence (nothing restricted by licensing). What the
licence gives (`features`, `modules`, `platforms`), what the site switched on (`apps`, `industries`) and what the
user's roles allow are kept apart: clients still ask Frappe for document permissions — `user.roles` is for
display. Cache by `digest`.

**Short block** — the `licence` object above — is also in the payloads the apps already load, so they can show a
read-only / expiry notice without another call: VanSaleX `vansalex.me.context` → `data.licence`, ZatGo POS
`pos_settings.get` → `data.licence`, MyBis `mybis.context.get_context` → `data.licence`. It never fails the
payload (`safe_licence_block`: an error is logged and `"error": true` returned). Older app builds ignore the
extra key; reading it is a client-side change in each app's own repository (not done here).

**Platforms are enforced on the server**: with a licence, a feature none of whose platforms the licence includes is
not in the entitlement (`Entitlement.from_features(platforms=...)`) — e.g. VanSaleX's mobile-only modules on a
Desk-only licence; an app whose feature drops out is off, so its API answers 404 like a switched-off app.

## Audit, coverage and hardening (Phase 9)

**Audit trail** (`Audit Log`, brief Part 17): edition field and feature changes, edition imports, licence
imported / replaced / rejected (with reason code) / verification failed / revoked, licences and revocation lists
issued, site identity created, and **site_config changes** — enforcement switch, issuer mode, signing-key
configured or not, site ID, clock tolerance — detected by `licensing/watch.py` (daily job and every Licence page
load; `doctype_name` "Licence Config"). App switch changes were already audited by ZatGo System Settings. Never a
key or a licence file in a log. Role permission changes stay with Frappe's own history (not duplicated).

The log is **append-only** (`zg_audit_log.py`): an existing entry cannot be changed by any route; an entry typed in
through the Desk or REST is refused (the system writes them in code), so none can be forged; licensing entries
cannot be deleted; other entries keep the old System Manager rule. Install / migrate / patches are exempt.

**API coverage** (`licensing/api_coverage.py`): every whitelisted `zatgo_core.api.v1` endpoint is owned by a
feature, an app or an industry — or listed in `NOT_LICENSED` with its reason (health checks, platform
administration, licensing itself, the Space subscription, portals, client sync, and the delivery / fleet products
that are not in the registry yet). `test_licensing_api_coverage` fails on a new endpoint without a decision and on
stale entries. Whatever the classification, documents an endpoint writes still pass the document-level gate.

**Hardening**: licence / revocation files over 256 KB and edition files over 1 MB are refused before parsing;
every licensing endpoint refuses Guest, and all but the client contract refuse a user without a ZatGo or System
Manager role — the permission check comes before the request is read (a test calls each endpoint).

### Brief Part 18 — where each test lives

| # | Area | Test |
|---|---|---|
| 1-5 | editions, registries, dependencies | `unit/test_licensing_registry`, `unit/test_licensing_editions`, `integration/test_licensing_registry`, `integration/test_licensing_editions` |
| 6-10 | edition / licence / role permissions, intersection, direct DocType access | `unit/test_licensing_gate`, `integration/test_licensing_enforcement` |
| 11-12 | REST / whitelisted methods | `integration/test_licensing_api_coverage`, `test_licensing_enforcement` (Administrator in a request) |
| 13-14 | reports / print | allowed by design (D6) — `unit/test_licensing_gate::test_read_print_and_cancel_are_never_refused` |
| 15-20 | signature, tampering, expiry, trial, perpetual, wrong site | `unit/test_licence_format`, `unit/test_licence_policy`, `integration/test_licensing_licences`, `integration/test_licensing_policy` |
| 21-23 | downgrade, upgrade, existing data kept | `integration/test_licensing_money_path::test_upgrade_then_downgrade_keeps_history` |
| 24-28 | Sales Invoice + GL, Stock Entry + SLE, Payment Entry, sales and purchase returns | `test_licensing_money_path`, `test_licensing_enforcement` |
| 29 | multi-company | company limit in `test_licensing_policy`; the licence is site-wide (no per-company grant) |
| 30 | migration safety | every phase migrated the local test site; new DocTypes only, no data patches |

## Phase 10 additions

- **Records ERPNext creates inside another record's own save.** Creating a Company (allowed by the foundation)
  makes ERPNext create its chart of accounts, warehouses, cost centers, departments and tax templates in the same
  save. Found by test: under a Sales licence that creation was refused ("does not include create for Account").
  `gate.CASCADES` now exempts exactly those DocTypes while a permitted Company is being saved, and the exemption
  ends in the Company's `on_update` hook (`gate.end_cascade`), so a Stock Entry in the same request is still
  refused. Add a parent here if another ERPNext flow turns out to create masters as a side effect.
- **Usage audit** (`licensing/usage_audit.py`): read-only report of what a site created in the last N days that an
  edition would refuse; the tool for choosing an edition before enforcing. `bench --site X execute
  zatgo_core.licensing.usage_audit.report --kwargs '{"edition_id": "sales"}'`.
- **Runbook**: `licensing_rollout.md`.
