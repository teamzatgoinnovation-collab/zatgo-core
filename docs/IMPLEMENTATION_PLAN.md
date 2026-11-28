# Implementation plan

*Phases 1–2 output, 2026-11-28. Nothing in this plan has started. Every phase begins only after the previous one is verified and, for Phase 3 onwards, after you approve `TARGET_ARCHITECTURE.md` and the open decisions in `ARCHITECTURE_DECISIONS.md`.*

## Gate 0: before any code (needs you)
| # | Item | Why |
|---|---|---|
| G-1 | Each session commits or drops its uncommitted work (T-04) | 40 files overlap DocTypes, patches and workspaces we will touch |
| G-2 | Decide the DocType naming direction (ADR-005: `ZG` prefix vs `rename-zatgo`) | Phase 4 and every later phase depend on it |
| G-3 | Decide module availability (ADR-003: extend switches + licensing, or a new store) | Phases 5–8 depend on it |
| G-4 | Approve pushing `main` (6 licensing commits are local only) | A clean base for branches and CI |
| G-5 | Review role holders on kasibasia and democompanysa (T-12) | Live rights changed on 11-06 |

## Priority 1: fixes worth doing before the redesign
Each is small, has a test, and changes no schema except where noted.

| ID | Fix | Finding |
|---|---|---|
| F-1 | Tax template on accounting API invoices; `client_id` required on money endpoints; invoice-from-quotation duplicate check | T-01, S-01 |
| F-2 | Replay checks (state + payload) on every VanSaleX replay | S-02 |
| F-3 | Signature tests for every core-method override; forwarding helper | C-01 |
| F-4 | Green test baseline: isolate MyBis tests, remove stale bench files, smoke tests for untested API modules | T-13 |
| F-5 | Release identity: one version source, tag `v0.5.0`, full-tree deploy from a tag after md5 check; bring server-only code into git or remove it | T-03, T-05 |

## Phase roadmap (your Phases 3–15, adapted to the existing app)
| Phase | Scope here | Builds on (already exists) | Exit criteria |
|---|---|---|---|
| 3 Core framework | `services/` shared layer only where duplication is proven: `availability` resolver, `erpnext_adapter` (C-02), `errors` (one API error shape, already `api/response.py`), `audit` (wrap `ZG Audit Log`), `docs_service` (idempotent create/submit, i.e. `idempotency.py` + `submit_or_rollback`). No new package tree. | `api/response.py`, `validators.py`, `idempotency.py`, `row_scope.py`, `app_gate.py` | unit and integration tests per helper; no behaviour change (suite unchanged) |
| 4 DocTypes and database | `DOCTYPE_CATALOG.md`, `DATABASE_ARCHITECTURE.md`, `MIGRATION_PLAN.md`; naming per ADR-005; integrity checks (orphan links, duplicates, unused DocTypes such as ZG Application Registry) as read-only reports first | 84 DocTypes, `test_naming_standard.py` | catalog complete; no rename until the migration is rehearsed on a copy of each production database |
| 5 Modules | ZG Module Settings per ADR-003: enable/disable with dependency validation, mapped to the licensing module ids; API 404 + DocType gate for ZatGo features; ERPNext core untouched | `app_catalog`, `app_state`, `licensing/registry`, `industries` | disable never deletes data; API refuses disabled features (security test); dependency test |
| 6 Desk and workspaces | Module workspaces (Home, Sales, Purchase, Stock, Accounting, Production, Quality, Service, HR, Reports, Settings) as synced files; sidebar from module and role; per-customer = enabled modules + roles | `app_sidebar`, ZatGo ERP workspace, folder in `boot.py` | three example customers (A/B/C) reproduced on testerp by settings only |
| 7 Settings | One settings landing page (extend `zg_app_hub` / General Settings) with sections; native ERPNext settings linked, not copied; ZatGo Singles per area | ZG System / POS / VanSaleX / Company Settings, `settings_service` | no setting overrides business data; S-04 fixed; T-10 resolved |
| 8 Permissions | Roles for the example personas; Warehouse/Company User Permissions; a "Frozen Stock" pattern via Item Group User Permission; explicit unauthorized-access tests for Desk, API, reports, exports, jobs | DocPerms, `row_scope`, owner scope, VanSaleX backstop | a negative test per persona and route |
| 9 Business logic | Review VanSaleX, POS and accounting rules against ERPNext lifecycles; cancellations, returns, duplicates | existing money-path tests | stock and GL effects tested per flow |
| 10 Reporting | Native Script Reports and Dashboard Charts per area, company/warehouse/date filters, User Permission aware | Business Summary, MyBis queries, ZatGo ERP Number Cards | no mock data; `EXPLAIN` per report query |
| 11 UI | Theme tokens with brand `#2952E3` / `#5B7FFF`, empty, loading and error states, dark mode where supported | `saas_theme` partials, `zg_components.css` (untracked) | browser check light and dark, phone and desktop |
| 12 Security and performance | S-03…S-16, P-01…P-08, measured before and after | — | report with numbers |
| 13 QA | Fresh install, upgrade from each live commit, multi-company, multi-site, failure recovery; CI (T-14) | 1,514 tests | coverage report; green CI |
| 14 GitHub distribution | Clean-site install from GitHub, tags, README, install docs, uninstall safeguards | `pyproject` pins, `before_install` | install and upgrade verified on a fresh bench |
| 15 Release | Runbooks (deploy, backup/restore, rollback, migration checklist), compatibility matrix, admin and developer guides; `v1.0.0` | `docs/deployment.md`, `licensing_rollout.md`, `deploy-staging/` | release checklist signed off; no live deploy without your approval |

## Rules for every phase
- Research first and report findings before changing anything.
- Small commits, one logical change each, with tests.
- Local bench first, then testerp, then client sites one at a time, each after your approval.
- Never modify ERPNext core files.
- Never delete or rename a DocType or field without a rehearsed, data-preserving patch.
- Keep whitelisted method paths stable: clients call them by path (`compat_methods.OLD_METHOD_PATHS` for moves).
