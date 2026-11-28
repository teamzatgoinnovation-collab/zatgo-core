# Technical audit

*Phase 1, 2026-11-28, `main` at `d5bc17b`. Security, performance and compatibility have their own documents. `IMPLEMENTATION_PLAN.md` orders the work.*

**Evidence**:
- **Verified**: seen at runtime (local bench or testerp).
- **Read**: confirmed in today's code.
- **Carried**: from the 2026-10-23 or 11-06 audit and not re-checked today.

**Severity**: CRITICAL / HIGH / MEDIUM / LOW / INFO. No finding is CRITICAL: none lets an unauthenticated caller reach data or money.

**Priority**: P1 next, P2 soon, P3 when the area is touched.

## Summary
| Severity | Technical | Security | Performance | Compatibility |
|---|---|---|---|---|
| HIGH | 4 | 2 | 0 | 3 |
| MEDIUM | 10 | 10 | 4 | 4 |
| LOW / INFO | 7 | 4 | 4 | 3 |

What is sound and should be kept:
- ERPNext stays the ledger.
- Idempotent creates are backed by unique indexes and race recovery.
- Self-healing setup steps.
- One app catalog.
- Gated hook wrappers for bundled modules.
- Licensing is dormant by default.
- Parameterised SQL, with interpolated identifiers listed and tested for MyBis.
- 1,514 tests.

## Findings
| ID | Sev | Area / file | Existing behaviour → problem | Business impact / technical risk | Recommended solution | Prio | Evidence |
|---|---|---|---|---|---|---|---|
| T-01 | HIGH | Accounting API: `services/erpnext_writes.py` `create_sales_invoice`, `create_purchase_invoice` | Builds the document with no tax template. On a VAT-registered company the invoice posts with 0 VAT. | Under-charged VAT, a ZATCA risk for web/desktop accounting users. | Apply the company's tax template the way the van-sale path does (`vansalex_settings.sales_tax_template`); `client_id` required on money endpoints; check what the clients send. | P1 | Verified 11-06 (testerp S1-20) |
| T-02 | HIGH | Naming: branch `rename-zatgo` vs `main` | `main` still has `ZG <Name>`. `rename-zatgo` drops the prefix (with migration patch `v0_6_0`) and runs live on `signxdemo`; the four client sites still have `ZG` names. | Two DocType vocabularies until the lines are joined; every fix made on `main` must be re-made with the new names. | **Decided 2026-11-28: no `ZG` (ADR-005).** Make the rename line the base; rehearse `v0_6_0` on copies of the client databases; add a name-collision guard for the generic names. | P1 | Read |
| T-03 | HIGH | Deploy process | Production is deployed with delta tars. The tree drifts from git: Settings Map files exist only on the server; `zg_pos_settings.py` has an audit mixin that git lacks; `defaults.py` is behind git. | A full sync silently removes server-only code; nobody can say which commit a site runs. | A release = a tag; deploy the whole tree from the tag after an md5 check; bring the server-only code into git or remove it on purpose. | P1 | Verified 11-06 |
| T-04 | HIGH | Working tree | 40 modified files and 4 untracked paths from several sessions, overlapping DocType JSON, patches and workspaces. | Lost work, or a mixed commit; `patches.txt` lists `v0_5_1`, which exists only untracked. | Each owner commits or drops its work before Phase 3. | P1 | Read |
| T-05 | MED | Version | `__version__`, `setup.py` and `pyproject.toml` all say 0.4.0, while patches reach `v0_5_2` and licensing is complete. | Releases can't be identified. | SemVer with tags (Phase 14/15); one version source. | P2 | Read |
| T-06 | MED | Availability model | Six overlapping lists: app catalog switches, industries, licensing modules/features, ZG Feature Flag, plugin registry (ZG Registered Application, ZG Setting Section), legacy ZG Application Registry / Client Application. | Phase 5 would add a seventh. Admins see several "enable" screens. | One availability resolver over catalog + industries + licence (`TARGET_ARCHITECTURE.md` §4); retire Feature Flag and Application Registry by projection, not deletion. | P2 | Read |
| T-07 | MED | Layering: `api/v1/delivery/stops.py` (590 lines), parts of `vansalex/orders.py`, `vansalex/admin.py`, `resto_pos/kds_tickets.py` | Status machines, points and queries inside API handlers. | Harder to test and reuse; logic gets duplicated. | Move into `services/` behind the existing thin-handler pattern (`api/v1/mybis/_common.run` is the model). | P3 | Read |
| T-08 | MED | Large units | `setup/ensure_print_formats.py` 2,500 lines; `services/erpnext_writes.py` 2,026; `vansalex_service.py` 1,679; `chat_ai/erpnext/orchestrator.py` `run_turn` 480 lines. | Review and change risk. | Split by document type or format when next touched; no big-bang rewrite. | P3 | Read |
| T-09 | MED | Error handling | About 50 `except Exception: pass`; setup steps log and continue. | Silent failures, for example a print format or permission step that never applied. | Log with context at minimum; return a failed-steps list to `deploy_check`. | P2 | Read |
| T-10 | MED | Settings without effect: `ZG Security Settings` | Password, 2FA and lockout fields are never read. | Admins believe a policy is enforced. | Wire each field to Frappe's own System Settings, or hide it with a note. | P2 | Carried (M6) |
| T-11 | MED | Migrate overwrites configuration | Print formats, some Custom DocPerms, registry rows and Desk icons are re-asserted on every migrate. | A customer's Desk edits are lost on upgrade. | Seed-once markers (the pattern `ensure_vansale_perms` now uses) for everything a customer may edit. | P2 | Carried (M13) |
| T-12 | MED | Permission repair (11-06) | Restored the standard ERPNext roles on Sales Invoice, Sales Order and others, including on the hand-tuned sites (kasibasia, democompanysa). | Users holding Accounts User or Sales User gained rights that were never reviewed. | Review role holders per site (query in `audit_2026-11-06.md`); remove rows an admin does not want (they stay removed). | P1 | Verified 11-06 |
| T-13 | MED | Tests | 40 suite failures pre-existing on the local bench (16 stale Settings Map files, 18 non-isolated MyBis totals, others); 13 API modules never named in a test (journals, purchase_invoices, quotations, leads, tickets, kds_tickets, boys, tracking, visits, catalog_data, employees, item_groups). | A red baseline hides regressions. | Make MyBis tests use their own company; delete the stale bench files; endpoint-discovery smoke tests like `test_mybis_security`. | P1 | Verified 11-06 / Read |
| T-14 | MED | No CI | Tests run by hand on a shared local bench. | Regressions found late; sessions collide on one bench. | A CI job with a throwaway bench (GitHub Actions + frappe/bench image). | P2 | Read |
| T-15 | LOW | Dependencies | `anthropic>=1.0` and other lower-bound-only pins; `setup.py` duplicates `pyproject.toml`. | An SDK major can break Chat AI on a rebuild. | Compatible-release pins; drop `setup.py` metadata duplication. | P2 | Read |
| T-16 | LOW | `hooks.py` import-time loop | `DUPLICATE_PREVENTION_DOCTYPES` appended to `doc_events` in a loop. | Works, but hides registrations from readers. | Build the dict with a helper. | P3 | Read |
| T-17 | LOW | Fixtures | Only Role is a fixture; custom fields, perms and property setters come from code. | Fine: deliberate self-heal. Undocumented for newcomers. | Document it (done in `CURRENT_ARCHITECTURE.md`). | — | Read |
| T-18 | LOW | Uninstall | `before_uninstall` removes Desk leftovers only; custom fields created without `module`, Custom DocPerms and property setters stay. | An uninstalled site keeps ZatGo columns (data preserved, which is correct). | Document it; offer an explicit, confirmed cleanup command, never automatic. | P3 | Read |
| T-19 | LOW | Translations | `ar.csv` has 38 lines. | Arabic UI mostly untranslated. | Extract strings (`bench get-untranslated`) per release. | P3 | Read |
| T-20 | INFO | Documentation | 31 topic docs plus audits, some stale (`architecture.md`, `folder_structure.md`, `doctypes.md` covers a third of the DocTypes). | Contradictions. | These phase documents supersede them; fold the old ones in during Phase 15. | P3 | Read |
| T-21 | INFO | Cross-session work | Several Claude sessions edit the same checkout, bench and server (one killed a migrate on 11-06). | Collisions. | One owner per area; a deploy lock (`deploy.sh` waits on bench.log, but not on restarts). | P2 | Verified 11-06 |
