# Editions and licensing

Status: **Phase 2 of 10 — the module / feature registry.** Nothing is enforced yet: no hook, permission or
API answers differently because of this code. Audit and decisions: `licensing_audit_2026-11-17.md`.

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

## Next phases
3 editions + dependency inspector · 4 enforcement in the existing hooks (behind the per-site switch, off) ·
5 licence format, Ed25519 issuer and verification · 6 licence workspace · 7 expiry/trial into
`subscription_gate`, limits · 8 one client capability payload · 9 audit, endpoint coverage, money-path tests ·
10 rollout.
