# Editions, licensing and subscriptions — Phase 1 audit (2026-11-17)

Scope: the brief "ZatGo ERP — unified edition, module, feature, permission, subscription and offline licensing
management". This is Phase 1 only: what exists, what ERPNext v16 already gives us, the conflicts, and a proposed
plan. **No code was changed.** Nothing below is implemented yet.

Checked against: `zatgo-core` main at `920aca8` (working tree also holds another session's uncommitted Duplicate
Prevention / Chat AI edits — untouched), the local dev bench (Frappe 16.29.0, ERPNext 16.31.0, hrms, crm,
zatca_integration, print_designer, space, space_cloud, zatgo_hub installed), and the repo's own docs
(`architecture.md`, `permissions.md`, `subscription.md`, `plugin_guide.md`, `industries.md`, `vansalex_access.md`,
the 10-23 and 11-06 audits). Production was not touched or read.

---

## 1. Current zatgo_core architecture

`zatgo_core` is the one extension app on every accounting / van-sale site. Layers: thin `api/v1/*` (349
`@frappe.whitelist` endpoints across ~30 product folders) → `services/*` → ERPNext controllers. Four modules
(`modules.txt`): ZatGo Core, Chat AI, Tracker, ZatGo Space. 55 DocTypes in the core module.

It already has an **app platform** that answers most of "what is this site allowed to run" — at app granularity:

| Concern | Where | What it does |
|---|---|---|
| Catalog of switchable apps | `services/app_catalog.py` + `<module>/app_manifest.py` + `plugins/manifests/core_apps.py` | One normalised list: key, group, switch field, `default_on`, `requires`, `api_prefixes`, workspaces, settings DocTypes, version. 11 apps today (core_settings, vansalex, saas_theme, language_switcher, vansalex_web, zatgo_pos, duplicate_prevention, industries, chat_ai, mybis, tracker, zatgo_space). |
| Is app X on | `services/app_state.py` | Only reader of the ZatGo System Settings switches (handles the Single-Check "0 vs unset" trap). |
| Server gate | `services/app_gate.py` | `before_request`: whitelisted methods under an off app's prefixes → 404; `@app_api`, `require_app`. |
| DocType gate | `services/bundled_apps.py` | `has_permission "*"` + `permission_query_conditions "*"`: documents of a switched-off *bundled module* are nobody's / `1=0`. |
| Who may switch | `services/app_authority.py` | System Manager only, enforced in the ZatGo System Settings controller (form, REST and hub all bound). |
| Desk visibility | `services/app_desk.py`, `app_sidebar.py`, `core_sidebar.py`, `events/boot.py` | Hides workspaces / sidebars / rail icons of off apps; never deletes. |
| Industries | `industries/registry.py`, `industries/gate.py` | Second registry (jewellery, gym, restaurant, textile, supermarket) with capabilities + `requires_industries`, same three-layer gate. |
| Feature catalog (one app) | `services/vansalex_access.py` | VanSaleX's own module/feature keys (`VanSaleX Settings.access` rows + per-user switch-offs), enforced in every `api/v1/vansalex/*` endpoint and by a DocType backstop for field users. |
| POS pages | `ZatGo POS Settings → Pages` | Which POS app pages a site shows. |
| Feature flags | `Feature Flag` + `services/feature_flag_service.py` | Rollout flags (status, company/branch, rollout %). Not a licensing mechanism; little used. |
| Plugin registry | `Registered Application`, `Setting Section`, `plugins/discover.py` | Projection of the catalog for client apps; `enabled` always follows the switch. |
| Audit | `Audit Log` + audit mixin | Every settings mutation logged (passwords redacted); delete restricted to System Manager. |

Design rules already established and documented (and which this project must keep): *one rule per concern*
(no parallel registries), *off is not uninstalled*, *fail-open for unmanaged sites*, *site-optional Desk assets via
`before_request`, never `app_include_*`*, *new DocTypes are `ZG <Name>`*.

## 2. Existing DocTypes relevant to this brief

Nothing named Product / Edition / Module / Feature / Licence / Subscription / Site Registration exists in
zatgo_core. Closest existing pieces, which the new design must reuse or absorb rather than duplicate:

- `ZatGo System Settings` (Single): app switches, industries table (`Enabled Industry`).
- `Registered Application`, `Setting Section`, `Application Registry`, `Client Application`,
  `Application Settings` (`client_apps`: which front-ends may talk to the site — advisory only).
- `Feature Flag`.
- `VanSaleX Settings` + `VanSaleX Access` / `Van Sale Profile Access`.
- `Config Profile`, `Config History` (settings versioning/history).
- `Audit Log`.

Outside zatgo_core: the **`space` app** (Space platform, separate repo, zatgoportal site) owns `Space Plan`
(with `allowed_apps`), tenants, subscriptions, payments and the lifecycle (trial / read-only / inactivity
deletion). `zatca_integration` (separate app) owns e-invoicing.

## 3. Existing subscription and licensing implementation

**Licensing: none.** No licence file, no signature, no site identity, no user/company limits. Grep for
licen[cs]e / ed25519 / nacl / cryptography finds only unrelated hits.

**Subscription: yes — online, pushed by the platform** (`services/subscription_gate.py`, `docs/subscription.md`,
built 11-07):

- Source of truth is the Space platform. It writes `zg_subscription` into the site's `site_config.json` via
  `bench set-config` — a file only the bench user can write, so no in-site user (System Manager / Administrator
  included) can extend a trial. Dates travel with the state, so expiry is enforced locally if a push is missed.
- No `zg_subscription`, or `enforcement_on: 0` → unrestricted (fail-open by design).
- Rule: read-only when status is EXPIRED / SUSPENDED / PENDING_PAYMENT / DELETION_SCHEDULED / DELETED, or TRIAL
  past `trial_ends_at` unpaid, or ACTIVE more than `grace_days` (default 3) past `paid_until`.
- Enforcement in three layers: `before_request` (REST write verbs + a list of known write methods → 403),
  `has_permission "*"` (write ptypes answer no), `doc_events "*"` (every insert/save/submit/cancel/trash,
  `ignore_permissions` or not). Exempt: log/queue DocTypes, a user's own User record, install/migrate/patch.
  `guard_job` wraps writing scheduler jobs.
- Known, documented gap: raw SQL / `db.set_value` / `db_set` fire no document event.
- Desk: boot payload → heart badge by the sidebar user (trial days left / read-only notice).
- `services/activity.py::last_human_activity` feeds the platform's inactivity clock.
- Production (per notes of 11-07): deployed with **enforcement OFF, auto-deletion OFF, e-mail OFF**, Protected
  Domains set for the real company sites (kasibasia, democompanysa, accounting, testerp, zatgoportal).
  Round-2 fixes are pushed but not deployed. End-to-end read-only enforcement on a real tenant is **not verified**
  in production.

So the brief's "one-month trial, show remaining days, after expiry block create/update and allow view" **already
exists** for Space-hosted sites. The inactivity / deletion policy the brief asks to review lives in the `space`
app (`services/lifecycle.py`, `jobs/lifecycle.py`) and is already default-off with protected domains, multiple
warnings and dry-run events. What is missing is the **offline** path (self-hosted sites with no platform push).

## 4. Existing permission customisations

| Hook | Targets | Purpose |
|---|---|---|
| `before_request` | all | subscription write gate, app API gate (404), industry API gate, Desk includes |
| `has_permission "*"` | all DocTypes | subscription (writes), bundled-module DocTypes, industry DocTypes |
| `permission_query_conditions "*"` | all DocTypes | bundled-module rows, industry rows |
| `has_permission` / query per DocType | Device Token, User Preferences (owner), Tracker (Project/Task/Issue/Timesheet), 9 AI DocTypes | owner / module scoping |
| `doc_events "*"` | all | subscription write gate (7 events), Chat AI hooks |
| DocType backstop | Sales Invoice/Order, Stock Entry, Payment Entry (field users) | VanSaleX feature switches |
| `services/row_scope.py` | API reads using SQL | Company User Permission applied in SQL, portal party scope |
| `ensure_vansale_perms` | many ERPNext DocTypes | seeds Custom DocPerm once, copying standard rows first |
| `override_whitelisted_methods` | printview, PDF, query_report run/export, search_link | print format choice, report templates, link search |

Every one of them returns **True (never None)** when it has no objection — None is a denial in Frappe v16
(`feedback_frappe_merge_gotchas`). Any new `"*"` hook must follow that, be cheap (it runs on every permission
check), and be exempt during install/migrate.

## 5. ERPNext v16 / Frappe functionality to reuse

| Need in the brief | Native mechanism | Use it for |
|---|---|---|
| Layer 3 (user role) | Role, DocPerm / Custom DocPerm, Role Permission Manager, User Permission, Role Profile | Unchanged. Editions never write DocPerms. |
| Per-user module hiding | **Module Profile** + User `block_modules` | Optional convenience for admins only — see conflict C3 for why it cannot carry edition/licence. |
| Domains | Domain / Domain Settings / Has Domain | Legacy (restricts roles/sections by business domain). Not a fit for commercial gating; don't revive. |
| User limits | User Type (System vs Website), `frappe.get_all("User", {"user_type": "System User", "enabled": 1})` | Counting licensed users. |
| Cryptography | `cryptography` 46.x is already a **Frappe dependency** (`frappe/pyproject.toml`) | Ed25519 sign/verify (`cryptography.hazmat.primitives.asymmetric.ed25519`) — no new package. |
| Workspace / sidebar / Desktop Icon visibility | already driven by `app_desk` / `app_sidebar` | Extend, don't rebuild. |
| Report permissions | Report `roles`, `frappe.desk.query_report.run` (already overridden) | Report-level gate goes in the existing override. |
| Print | printview / download_pdf (already overridden) | Print gate goes in the existing override. |
| Audit | Version, Activity Log, `Audit Log` | `Audit Log` for licence/edition events. |

What ERPNext does **not** provide: a commercial edition/licence concept. There is also no Gate Entry / Gate Pass
DocType anywhere on the bench, and no India-GST app (india_compliance) installed — so brief modules **L (Gate
Management)** and the **GST / India tax** parts of **M** have no existing implementation to register. Per the
brief's own rule ("register actual existing functionality only") they would be omitted, not built.

## 6. Existing integrations and dependencies that consume this

- **VanSaleX** (Flutter, `mobile/flutter-vansalex`, `/vansalex` web, Capacitor shell): reads `me.context.access`.
- **ZatGo POS** (`desktop/zatgo-pos`): `api/v1/pos_settings.get`, `pos_profile`, `retail_pos`, `resto_pos`.
- **Desktop / web accounting** (`desktop/desktop-accounting`, `web/web-accounting` via `packages/zatgo-packages`).
- **MyBis** (`mobile/mybis`): `api/v1/mybis/*`, switch `enable_mybis`.
- **Space platform**: pushes `zg_subscription`, reads `activity.last_human_activity`.
- **zatca_integration**: Sales Invoice hooks — must keep running under any edition that sells.
- **hrms** (overrides Payment Entry's class; HR/Payroll modules), **crm** (Frappe CRM app, distinct from
  ERPNext's CRM module).

A platform/feature contract for clients therefore already has four shapes (`me.context.access`,
`pos_settings.pages`, the app switch 404s, MyBis switch). Phase 8 should give them one shared
`effective_capabilities` payload, keeping the old shapes for older app builds.

## 7. Conflicts and risks

**C1 — On a customer site, the customer *is* the System Manager.** Every site has Administrator (password
policy: `admin` on all sites per the user's own choice) and the customer's own System Managers. Any edition,
module, feature or licence record that is an editable DocType on the customer site is controlled by the
customer. Therefore:
- The edition *builder* (brief Parts 2, 11, 12) cannot be the trust anchor on customer sites. Editions are a
  **vendor-side** artefact; on a customer site the only trusted input is the **signed licence payload** (which
  embeds the resolved module/feature/action set of its edition at issue time — this also satisfies "changing an
  edition template must not silently change active licences").
- Customer-side DocTypes (Licence etc.) hold the original signed bytes; every enforcement read re-derives
  from a verified payload (cached by payload hash), never from editable fields.
- The brief's "authorized ZatGo administrator" has no meaning on a customer site unless we make it one. Proposal:
  editing editions happens only where the issuer runs (C5).

**C2 — Two sources of commercial truth.** Space already pushes subscription state into `site_config`. An offline
licence is a second input. They must combine by one written rule — proposal: *effective restriction = the most
restrictive of the two*, each absent input = no restriction (keeps today's fail-open), and the licence adds
module/feature/limit gating that the Space push does not carry. Not resolving this would create two badges, two
read-only rules and two trial clocks.

**C3 — Module granularity does not match ERPNext modules.** Sales Invoice, POS Invoice, Payment Entry and GL Entry
are all in ERPNext's *Accounts* module; Purchase Receipt and Delivery Note are in *Stock*; Quality Inspection is in
*Stock*. Module Def / Module Profile / `block_modules` blocking is therefore far too coarse (blocking "Accounts" kills
selling). Edition features must map to **DocTypes + actions**, not Module Defs.

**C4 — Gating standard DocTypes can break posting.** Submitting a Sales Invoice creates GL Entry, Payment Ledger
Entry, Stock Ledger Entry, Repost Item Valuation, Bin updates, ZATCA records — all through ERPNext's controllers,
often as the session user. If an edition hook denied, say, `GL Entry` create or `Stock Ledger Entry` because
"Accounting" or "Inventory" is not licensed, a Sales-only edition could not submit an invoice. Rules required:
- Gate only **user-facing transaction / master DocTypes and actions**; ledger, child, system and
  controller-created DocTypes are never edition-gated (an explicit allow-list per feature, plus a global
  "never gate" list: GL Entry, Payment Ledger Entry, Stock Ledger Entry, Bin, Repost Item Valuation, Serial and
  Batch Bundle, etc.).
- **Read access to history is never removed** by an edition/licence change (brief Part 16) — downgrade restricts
  create/submit/amend, not read; cancellation of existing documents needs a decision (blocking cancel can trap a
  mistake; allowing it lets an unlicensed module be "used" via amend → see D6).
- Every enforcement path needs the same system-context exemptions as `subscription_gate` (install, migrate,
  patch, plus ERPNext-internal creation while another doc is being submitted).

**C5 — Where the private key and issuer live.** The brief forbids the key on customer servers, in site DBs and in
backups. zatgo_core ships to customer servers, so the issuer's *code* may live in zatgo_core (public verification
key + payload schema are shared anyway), but the *key* must live outside any site: a file path outside
`sites/`, read only on the issuer host. One-repo-per-app (`.claude/rules/git.md`) means a standalone issuer tool
would be a new repo. Options in D2.

**C6 — Existing sites have no licence.** Four production sites (two of them real customers) run today without one.
Turning licence enforcement on by default would lock them out. Must follow the `subscription_gate` pattern:
**no licence = legacy/unrestricted** until a per-site enforcement switch is set — and that switch itself must not
be in the customer's hands (site_config, written by the bench user, like `zg_subscription`).

**C7 — Site identity.** Options: site name (Host), an install-time UUID in `site_config.json` (survives backup
restore *to the same bench*, not copied by a DB backup), or a UUID in the DB (copied with every backup — a
restore elsewhere silently keeps the licence). Offline licences must bind to something the customer cannot edit
from Desk. Proposal: `site_config` UUID + site name; documented that a bench admin can copy both — offline
licensing is tamper-*evident*, not tamper-*proof*, against someone with shell access.

**C8 — Clock trust.** Offline expiry depends on the server clock, which the customer controls. Best effort only:
persist the highest timestamp ever seen (in site_config and DB) and treat a jump backwards beyond a tolerance as
"clock rollback → read-only until a fresh licence". Must be documented as non-cryptographic.

**C9 — Revocation offline.** Not possible in general. Replacement licences with a higher `licence_version` and an
optional signed revocation list imported locally are the only honest mechanisms.

**C10 — Performance of `"*"` hooks.** There are already three `has_permission "*"` and two query `"*"` hooks plus
seven `doc_events "*"`. A fourth must resolve from a per-request cached capability map (frappe.local), keyed by
the verified payload hash — no DB reads per check.

**C11 — 349 whitelisted endpoints.** Many custom endpoints run with `ignore_permissions`. DocType-level
`has_permission` does not cover them; the existing app API prefix gate (404) does, at app granularity. Each
licensable feature needs either an API prefix or an explicit `@feature_api("...")` decorator, plus a
`doc_events` backstop for writes (as `subscription_gate` does). A discovery test (like
`tests/integration/test_mybis_security.py`) should fail when a whitelisted endpoint has no declared feature.

**C12 — Three overlapping registries already.** `app_catalog`, `industries/registry`, `vansalex_access.CATALOG`
(+ POS Pages, + `Feature Flag`). The new Module/Feature registry must sit **above** them and reference them
(e.g. feature `vansalex.sales.credit_sale` → existing VanSaleX key), not copy them. Editions then *license* apps;
the site switch still decides whether a licensed app is *on* (`app_state` becomes "licensed AND switched on").

**C13 — Native permission layering vs. the brief's example.** The brief's final example (licence allows create,
role allows view → user can view only) is exactly how an extra `has_permission` hook behaves: Frappe ANDs hook
answers with DocPerms. No change to DocPerms is needed or wanted. Note that `has_permission` hooks cannot
*add* permission — they can only deny — which is what we want.

**C14 — Process risk.** Uncommitted Duplicate Prevention and Chat AI edits from another session are in this working
tree. `hooks.py` and `patches.txt` are already modified there (`patches.txt` + new `patches/v0_5_1/`). New phases
touch the same files, so they must wait for or coordinate with that session to avoid mixed commits.

**C15 — Brief vs reality, scope.** The brief lists ~15 DocTypes, a visual builder, import/export, comparison,
issuer, workspace, mobile/desktop contracts and 30 test areas. This is many weeks of work. Several modules
(Gate Management, GST/India) have nothing to register; HR/Payroll, CRM, Production are on the bench but not in
the workspace's active scope.

## 8. Proposed architecture (for approval — not built)

```
            VENDOR SIDE (issuer host, key file outside sites/)                CUSTOMER SITE
 ┌────────────────────────────────────────────────────┐        ┌──────────────────────────────────────────┐
 │ Module/Feature registry  (code, shipped in core)   │        │ same registry (code)                     │
 │ Editions (Edition + presets, editable here)     │        │ Licence (signed bytes, read-only)     │
 │ Edition builder + dependency inspector             │  .zgl  │ licence_service.verify() -> capabilities │
 │ Issuer: canonical JSON -> Ed25519 sign -> .zgl     │ ─────► │ capability_gate: request / has_permission│
 │ Licence History (issuer's own record)           │        │   / doc_events / report / print / API    │
 └────────────────────────────────────────────────────┘        │ app_state = licensed AND switched on     │
                                                               │ subscription_gate = min(Space, licence)  │
                                                               └──────────────────────────────────────────┘
```

- **Registry in code**, like `app_catalog`: `zatgo_core/licensing/registry/*.py` declaring modules → features →
  `{doctypes: {name: [actions]}, reports, pages, workspaces, api_prefixes, platforms, requires}` with stable ids
  (`sales.invoice.create`). Code because it describes code that ships; versioned with the app; testable (every
  DocType/report/page it names must exist — a unit test). DocTypes `Module` / `Feature` become read-only
  projections for the UI (like `Registered Application`), not authority.
- **Editions** (`Edition`, `Edition Feature`): data, editable only where issuer mode is on; 9 presets
  shipped as JSON fixtures; import/export as `edition.json` (unsigned, never trusted as a licence).
- **Licence** (`.zgl`): `{schema_version, product_id, licence_id, licence_number, licence_version, customer,
  site_ids[], edition_id, edition_version, features{id: [actions]}, limits{users, companies, sites}, type,
  issue/start/expiry, grace_days, platforms}` canonical JSON (sorted keys, UTF-8, no floats) + Ed25519
  signature, base64 envelope. Public key(s) in code with a key id, so keys can rotate.
- **Customer side**: `Licence` (the imported envelope, status, verification result; write only through the
  import service, System Manager), `Licence Activation` (history), events in `Audit Log`. Enforcement switch
  + site UUID in `site_config` (bench user only).
- **One capability gate** (`services/capability_gate.py`) implementing the brief's `is_feature_enabled`,
  `can_access_doctype`, `can_access_report`, `get_effective_permissions`, `validate_feature_access`, wired into the
  existing hook points (not new parallel ones), with the never-gate list from C4.
- **Subscription**: keep `subscription_gate` as the single read-only rule; feed it a second input (licence
  expiry / trial) instead of building another.

## 9. Decisions needed from the product owner

- **D1 — Trust anchor.** Accept that on customer sites only the signed licence is authoritative and edition
  editing happens on the issuer side only (C1)?
- **D2 — Issuer location.** (a) issuer mode inside zatgo_core on one internal ZatGo site, key file outside
  `sites/` (one codebase, Desk builder UI for free); (b) a separate CLI repo `zatgo-licence-issuer` (strongest
  isolation, no Desk UI); (c) inside the Space platform (zatgoportal) — online-side, also issues to Space tenants.
  Recommendation: (a), with the issuer site never exposed publicly.
- **D3 — Space vs licence precedence** (C2): "most restrictive wins"? Do Space-hosted tenants also get a signed
  licence (one model for both), or stay on the push only?
- **D4 — Default for unlicensed sites** (C6): legacy-unrestricted until enforcement is switched on per site?
- **D5 — Site binding** (C7): site_config UUID + site name, multi-site only when listed in the licence?
- **D6 — Downgrade semantics**: for features no longer licensed — read only (proposed); allow cancel of existing
  documents (proposed: yes, cancel allowed, amend refused, so mistakes can be reversed with an audit trail)?
- **D7 — Modules with no implementation** (Gate Management, GST/India): omit (proposed) or schedule as new
  product work?
- **D8 — Scope order**: which edition must work first? Proposal: Sales, Accounting, Inventory, POS, Enterprise
  (these map to what the active stack sells), HR/CRM/Production registered but not tuned.
- **D9 — User limit counting**: enabled System Users excluding Administrator and API-only users?
- **D10 — What happens when a limit is exceeded** (users/companies): block creating more (proposed), never
  disable existing users.

## 10. Proposed phase plan (each phase: local bench, tests, commit; deploy only on explicit go)

| Phase | Deliverable | Touches production behaviour? |
|---|---|---|
| 2 | Registry in code (modules/features/DocType+action maps, never-gate list, existence test); read-only `Module`/`Feature` projection | No |
| 3 | `Edition` + presets + dependency inspector (resolves required DocTypes/reports/settings, warns, never auto-adds paid modules) | No (issuer side only) |
| 4 | Capability gate wired into existing hooks, behind the per-site enforcement switch (off) | No until switched on |
| 5 | Licence format, Ed25519 sign/verify, issuer (per D2), tamper/wrong-site/expiry tests | No |
| 6 | Customer licence workspace: import, verify, overview, history, warnings (real actions only) | UI only |
| 7 | Licence expiry/trial fed into `subscription_gate` (per D3), limits (D9/D10), clock rollback | Only when enforced |
| 8 | One `effective_capabilities` client payload; VanSaleX/POS/MyBis read it, old shapes kept | No |
| 9 | Audit events, endpoint-coverage discovery test, money-path integration tests per edition (SI submit + GL, Stock Entry + SLE, PE, returns, multi-company) | No |
| 10 | Docs, deploy runbook (site_config keys, enforcement off by default), staged rollout on testerp first | Yes — explicit approval |

## 11. Verification status of this report

- **Verified** (read in code / on the local bench): every statement in sections 1–6 about zatgo_core files and
  hooks; Frappe 16.29.0 / ERPNext 16.31.0 versions; `cryptography` present as a Frappe dependency; absence of
  Gate Entry / Gate Pass DocTypes and of an India-GST app on the bench; presence of Module Profile, Domain, Role
  Profile, User Type DocTypes.
- **From earlier session notes, not re-checked today**: production deployment state of `subscription_gate` and
  Space lifecycle switches (OFF, Protected Domains set).
- **Not verified**: anything at runtime (no tests were run; this phase changed no code).
