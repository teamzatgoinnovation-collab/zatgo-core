# Editions and licensing

Status: **Phase 6 of 10 — the Licence page.** A site enforces its licence only when its `site_config` has
`zg_licence_enforcement` **and** a verified licence is imported; no production site has either yet, and no
production signing key exists until one is generated (see *Keys* below). Audit and decisions:
`licensing_audit_2026-11-17.md`.

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
- `sync.py` — projects the registry into `ZG Module` / `ZG Feature` on install and migrate.

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

## The projection: `ZG Module`, `ZG Feature`

Read-only DocTypes (core module) for the Desk and for Phase 3's edition builder to link to. Read for System
Manager, ZG Application Admin, ZG Read Only; nobody can create, change or delete a row — the controller refuses
any write outside the sync, `ignore_permissions` included. `sync_registry()` (from `install.after_migrate` and
`after_install`) writes a row only when the code changed, so a re-run writes nothing; a feature that left the
code is marked retired, never deleted. `available` = its source app is installed on this site.

## Adding a feature

1. Add it to the module's file in `catalog/` (`feature(...)`, real DocTypes / reports only).
2. Add its id to `catalog/ids.lock`.
3. Run `tests/unit/test_licensing_registry.py` (structure) and `tests/integration/test_licensing_registry.py`
   (everything it names exists on the site).

## Editions (Phase 3)

An **edition** is a commercial product configuration (`ZG Edition` + child `ZG Edition Feature`): which
registry features it includes — each optionally narrowed to fewer actions — on which platforms (Desk, desktop
apps, mobile apps), with which licence defaults (type, duration, trial days, maximum users / companies, 0 = no
limit) and suggested default roles. Foundation features are in every edition and are never listed.

It is a **template**. A licence (Phase 5) will carry its own signed copy of the resolved features, so changing
an edition never changes a licence that was already issued.

### Issuer mode (decision D2)
Editions are written only on the licence issuer site: `"zg_licence_issuer": 1` in its `site_config.json`
(`licensing/issuer.py`), and only by a System Manager. The `ZG Edition` controller enforces it, so the form, REST
and the builder page are all bound; on every other site editions are read-only. The private signing key
(Phase 5) will also live only there, outside `sites/`.

### Rules (`zg_edition.py`, `licensing/edition_config.py`)
- Features must be live registry features, not foundation ones; narrowed actions must be ones the feature grants.
- **Active** = no missing dependency. A Draft may miss some (its `Dependencies` tab lists them); nothing is ever
  added for it.
- The **version** goes up whenever what the edition grants changes (features, actions, platforms, licence
  defaults, default roles — `grant_hash`); renaming or a status change does not bump it.
- **Archived** editions cannot change until set back to Draft. Only a **Draft** can be deleted.
- Field changes and feature-table changes go to `ZG Audit Log` (derived fields are left out).

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
import is recorded in `ZG Audit Log` (`fieldname = import`, file hash).

### The page: **ZatGo Editions** (`/desk/zg-edition-builder`)
System Manager, ZG Application Admin, ZG Read Only may open it; only a System Manager on the issuer site can
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
licence. The signed file is recorded in **ZG Licence History** (number series `ZGL-.YYYY.-.#####`) and audited.
`revocation_list([licence ids])` signs a revocation list. API: `zatgo_core.api.v1.licensing.licences.
issue_licence / issued_licences / revoke_licences` (POST for writes; issuer + System Manager).

### Importing (customer site, `licensing/licences.py`)
`import_licence(file)`: signature with a trusted key → schema / product / dates / features → **site binding**
(this site's `zg_site_id` from `site_config`, created the first time the identity is read — never on migrate —
plus the site name when the licence lists names) → refuse a licence not started yet, expired, revoked, already
imported, or older than the version in force → store the original signed file in **ZG Licence** (it becomes
current) → audit. Refusals are audited with a reason code. `import_revocation(file)` marks listed licences
Revoked. API: `site_identity_info` (the IDs to send to the issuer), `current_licence`, `import_licence`,
`import_revocation`, `verify_licence` — System Manager for everything but reading.

### What the site trusts
Only the signed file. The entitlement (`entitlement._load` → `licences.current_entitlement`) is rebuilt from
the stored file — signature and site re-checked — and cached for an hour or until the next import / revocation.
A record edited in the database no longer verifies and gives the **foundation only**; so does a revoked
licence. `ZG Licence` and `ZG Licence History` cannot be written by hand (controller), and `ZG Licence` stays
writable on a read-only (lapsed subscription) site so a licence can reactivate it.

### Offline limits (stated, not hidden)
- Binding is tamper-evident, not tamper-proof: someone with shell access can copy `zg_site_id` and the site name.
- There is no central revocation: a signed revocation list or a replacement licence is imported like a licence.
- The clock is the server's: expiry and rollback detection belong to Phase 7. Until then an expired licence that
  was imported in time keeps giving its features, and a site with the switch on but no licence is unrestricted.

## The Licence page (Phase 6): **ZatGo Licence** (`/desk/zg-licence`)

In the ZatGo sidebar under General Settings, next to **Editions** (both are shortcuts of
`workspace/zatgo/zatgo.json`). Readers of ZG Licence (System Manager, ZG Application Admin, ZG Read Only) see it;
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
  events of ZG Audit Log (imported, rejected with reason, revoked, verification failed).
- **Actions** (menu): Import / Replace licence, Verify licence, Import revocation list, Export site identity
  (`zatgo.site_request` — the file to send ZatGo for a licence; creates the site ID the first time), Export
  licence information (`zatgo.licence_info`, a metadata backup — never importable), Download licence file.
- **Issuer section** (issuer site + System Manager only): Issue licence (Active editions; customer; site IDs —
  or load the customer's site identity file; type, dates and limits, blank = the edition's defaults) which
  downloads the signed file; every issued licence with Download, Replace (next version) and Revoke (downloads a
  signed revocation list).

API: `zatgo_core.api.v1.licensing.licences.get_page / site_request / licence_info / download_licence /
download_issued`, plus the Phase 5 endpoints. Data: `licensing/licence_overview.py`.

## Next phases
7 expiry, grace, trial and clock-rollback policy into `subscription_gate`; user / company limits enforced; "switch
on + no valid licence" policy · 8 one client capability payload · 9 audit, endpoint coverage, more money-path
tests · 10 rollout (real signing key, `public_keys.json`, staged switch-on).
