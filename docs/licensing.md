# Editions and licensing

Status: **Phase 3 of 10 — registry, editions and the dependency inspector.** Nothing is enforced yet: no
hook, permission or API answers differently because of this code. Audit and decisions:
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

## Next phases
4 enforcement in the existing hooks (behind the per-site switch, off) · 5 licence format, Ed25519 issuer and
verification · 6 licence workspace · 7 expiry/trial into `subscription_gate`, limits · 8 one client capability
payload · 9 audit, endpoint coverage, money-path tests · 10 rollout.
