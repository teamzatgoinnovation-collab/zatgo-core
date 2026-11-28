# Architecture decisions

*Started 2026-11-28 (Phase 2). Status: **Proposed** = awaiting your validation; **Accepted** = already the practice in code; **Open** = needs your choice.*

| ADR | Decision | Status |
|---|---|---|
| 001 | ERPNext is the system of record; zatgo_core never writes GL or stock ledger rows and posts through ERPNext controllers | Accepted (`.claude/rules/accounting.md`) |
| 002 | Evolve the existing structure; no `modules/<area>/` tree; a `services/core/` foundation only where duplication is proven | Proposed |
| 003 | Module availability: one resolver over installed apps, enabled modules, licence and user; `Module Settings` (one row per licensing module) holds enablement | **Accepted 2026-11-28** (product owner, Option A) |
| 004 | Workspaces: native Workspace + Workspace Sidebar records shipped as files and generated sidebars; per-customer navigation from modules and roles, never manual edits | Proposed (extends today's practice) |
| 005 | DocType naming: **no `ZG` prefix** (the `rename-zatgo` convention); `ZatGo <Name>` only where the plain name exists in Frappe/ERPNext | **Accepted 2026-11-28** (product owner) |
| 006 | Settings: ERPNext settings first; one ZatGo Single per area with Tab Breaks; no JSON blob; settings never rewrite existing documents | Proposed |
| 007 | Permissions: native roles, DocPerms, User Permissions and hooks; visibility separate from security; copy standard rows before any Custom DocPerm | Accepted (11-06 fix) |
| 008 | Releases: SemVer tags, one version source, full-tree deploy from a tag after an md5 check, CI on a clean bench | Proposed |
| 009 | Licensing registry ids are the stable module and feature ids for every other system | Proposed |
| 010 | Whitelisted method paths are a public API: never move one without a `compat_methods` entry | Accepted |

## ADR-002: evolve, don't restructure
- **Context.** The brief suggests `modules/sales/…`. Here, Frappe modules are DocType containers; the app already separates handlers (`api/`) from logic (`services/`).
- **Decision.** Keep the layout. Add `services/core/` for the shared foundation. Split oversized files when they are next changed.
- **Consequences.** No DocType `module` changes or import churn; client paths stay. The layout is less "textbook" than the brief.
- **Rejected.** A full move to `modules/`: it touches every DocType JSON, every import and client path, for no runtime benefit.

## ADR-003: module availability (Accepted 2026-11-28: Option A)
- **Context.** There are already three "is it on" systems: app switches, industries and licensing modules. Phase 5 asks for a module settings DocType with code, enabled, depends-on, order, icon, workspace and configuration.
- **Option A (recommended).** `Module Settings` (or `ZatGo Module Settings` if the plain name is taken) is a Single with one row per **licensing module id** (19 today, from the registry).
  - It stores `enabled`, `display_order`, `icon` and `workspace`.
  - `depends_on` is read-only, taken from the registry.
  - The controller refuses to disable a module others depend on, and refuses to enable one whose dependencies are off.
  - Today's `enable_*` app switches map onto rows through a migration patch that reads the existing values, so nothing changes for a site. `app_state` reads the new rows, with a fallback to the old fields during one release.
  - Disabling hides and gates; it never deletes.
- **Decision.** Option A, chosen by the product owner. Name per ADR-005: `Module Settings`, or `ZatGo Module Settings` if Frappe, ERPNext or an installed app already has the plain name (check at implementation). Rows link to the existing `Module` DocType, the registry projection formerly called `ZG Module`.
- **Option B (rejected).** Keep the switches as they are and add a module settings DocType only for ERPNext-area modules (Sales, Stock, …). This is simpler but leaves two enablement screens.
- **Option C.** A new registry independent of licensing. Rejected: a fourth system.

## ADR-005: naming (Accepted 2026-11-28: no `ZG` prefix)
- **Decision (product owner).** DocTypes carry no `ZG` prefix. A name that already exists in Frappe or ERPNext becomes `ZatGo <Name>`. Number Cards, Roles and the ERP summary block become `ZatGo <Name>`. This is what branch `rename-zatgo` implements (`f3b62d4`), and it is live on `signxdemo`.
- **How existing sites move.** `[pre_model_sync]` patch `v0_6_0/rename_zg_to_zatgo` uses `frappe.rename_doc` on 59 DocTypes. That renames the tables and repoints Link fields, child tables, DocPerms, Custom Fields and Property Setters. It is idempotent: it skips a name already renamed, and when both names exist it leaves the old one and reports it. It was tested on a `vansale1` upgrade (271 trips, 63 orders kept). Client sites (accounting, democompanysa, kasibasia, testerp) still have `ZG` names and move with this patch on their next migrate of the rename line.
- **Exceptions.** The 7 `ZatGo <Name>` DocTypes: Vehicle, Delivery Stop, POS Settings, System Settings, Notification Settings, Security Settings, Mode of Payment Account. The 25 legacy names (VanSaleX *, AI *, Tracker *, Space *) were never `ZG` and are unchanged.
- **Risks to manage.**
  1. Generic names (`Order`, `Table`, `Trip`, `Module`, `Feature`, `Edition`, `Licence`, `Audit Log`, `Device Token`, `Service Ticket`) can collide with a DocType of another app on the same bench. Add a `before_install` / migrate check that refuses when an installed app already owns one of our names, plus a unit test of the list against Frappe, ERPNext, hrms and the apps on our benches.
  2. Every reference by name (hooks keys, raw SQL table names, workspaces, JS routes, client code, the other sessions' 40 uncommitted files written with `ZG` names) has to move in the same release.
  3. `docs/naming.md` on `rename-zatgo` still states the old "`ZG <Name>`" rule and must be rewritten.
- **Consequence for the branches.** `licensing-phase10-on-rename` = `rename-zatgo` + the licensing commit `main` also has (`7ed8889` ≡ `d5bc17b`). The no-prefix line is the current code; `main` is the older line. Proposed: that line becomes `main` (with these phase documents re-applied), after the uncommitted work in this checkout has moved to it.

## ADR-008: releases
- Today, deploys are delta tars and the server drifts from git (T-03).
- Proposed: tag `vX.Y.Z` on `main` → build from the tag → `deploy.sh` checks the whole tree against the previous tag → deploy → migrate testerp → migrate client sites with approval.
- Version source: `zatgo_core/__init__.py`, with `pyproject.toml` reading it (or set once at release).
