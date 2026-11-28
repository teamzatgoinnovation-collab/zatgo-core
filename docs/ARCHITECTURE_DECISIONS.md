# Architecture decisions

*Started 2026-11-28 (Phase 2). Status: **Proposed** = awaiting your validation; **Accepted** = already the practice in code; **Open** = needs your choice.*

| ADR | Decision | Status |
|---|---|---|
| 001 | ERPNext is the system of record; zatgo_core never writes GL or stock ledger rows and posts through ERPNext controllers | Accepted (`.claude/rules/accounting.md`) |
| 002 | Evolve the existing structure; no `modules/<area>/` tree; a `services/core/` foundation only where duplication is proven | Proposed |
| 003 | Module availability: one resolver over installed apps, enabled modules, licence and user; `ZG Module Settings` holds enablement | **Open** |
| 004 | Workspaces: native Workspace + Workspace Sidebar records shipped as files and generated sidebars; per-customer navigation from modules and roles, never manual edits | Proposed (extends today's practice) |
| 005 | DocType naming: `ZG` prefix (`main`) vs no prefix (`rename-zatgo`) | **Open** |
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

## ADR-003: module availability (Open)
- **Context.** There are already three "is it on" systems: app switches, industries and licensing modules. Phase 5 asks for `ZG Module Settings` with code, enabled, depends-on, order, icon, workspace and configuration.
- **Option A (recommended).** `ZG Module Settings` is a Single with one row per **licensing module id** (19 today, from the registry).
  - It stores `enabled`, `display_order`, `icon` and `workspace`.
  - `depends_on` is read-only, taken from the registry.
  - The controller refuses to disable a module others depend on, and refuses to enable one whose dependencies are off.
  - Today's `enable_*` app switches map onto rows through a migration patch that reads the existing values, so nothing changes for a site. `app_state` reads the new rows, with a fallback to the old fields during one release.
  - Disabling hides and gates; it never deletes.
- **Option B.** Keep the switches as they are and add `ZG Module Settings` only for ERPNext-area modules (Sales, Stock, …). This is simpler but leaves two enablement screens.
- **Option C.** A new registry independent of licensing. Rejected: a fourth system.

## ADR-005: naming (Open)
- **Facts.**
  - `main` has 59 `ZG ` DocTypes plus 25 legacy names, enforced by a test.
  - The production client sites (accounting, democompanysa, kasibasia, testerp) run `main`'s names.
  - `rename-zatgo` removes the prefix ("ZatGo" only where ERPNext has the name) and runs on `signxdemo` only.
- **Option A (recommended).** Keep `ZG` on `main`. Retire `rename-zatgo`. Migrate `signxdemo` with a rename patch, rehearsed on a copy of its database. Optionally rename the 25 legacy names (VanSaleX Settings, AI *, Space *, Tracker *) later, with `rename_doc` patches. That makes your Phase 4 examples (ZG Settings, ZG Audit Log) consistent.
- **Option B.** Adopt `rename-zatgo`. That means renaming 59 DocTypes on four client sites: high risk for a cosmetic gain, and it contradicts the brief.

## ADR-008: releases
- Today, deploys are delta tars and the server drifts from git (T-03).
- Proposed: tag `vX.Y.Z` on `main` → build from the tag → `deploy.sh` checks the whole tree against the previous tag → deploy → migrate testerp → migrate client sites with approval.
- Version source: `zatgo_core/__init__.py`, with `pyproject.toml` reading it (or set once at release).
