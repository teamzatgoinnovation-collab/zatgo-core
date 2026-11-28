# ZatGo Core — project overview

*Phase 0 discovery, 2026-11-28. Describes `main` at `d5bc17b`. Read from the code; nothing was run for this document.*

## What it is
`zatgo_core` is one Frappe app (Desk title **ZatGo**) that extends ERPNext v16 for ZatGo's customers in Saudi Arabia. It is the server side of every ZatGo client and the home of several products that used to be separate apps:

| Product | Kind | Switch |
|---|---|---|
| ZatGo ERP workspace (Accounts & Inventory) | Desk workspace over ERPNext screens | always on |
| VanSaleX (van sales) | API + settings for the Flutter app and its `/vansalex` web build | `enable_vansalex` (default on) |
| ZatGo POS (retail and restaurant counter) | API + settings for the Electron POS | `enable_zatgo_pos` (default on) |
| MyBis (management/BI) | read-only API for the MyBis app | `enable_mybis` (default off) |
| Duplicate Prevention | `validate` hook + rules | `enable_duplicate_prevention` (default on) |
| ZatGo AI (Chat AI) | in-Desk assistant, local models by default | `enable_chat_ai` |
| ZatGo Tracker | projects/tasks/time | `enable_tracker` |
| ZatGo Space | the SaaS platform's tenant side | `enable_zatgo_space` |
| Desk theme, language switcher | UI | `enable_saas_theme`, `enable_language_switcher` |
| Industries (Restaurant, Supermarket, Gym, Jewellery, Textile) | extra DocTypes/APIs per vertical | ZG System Settings → Industries |
| Editions and licensing | signed offline licences, editions, feature gate | dormant until a licence and `zg_licence_enforcement` exist |
| Subscription gate | read-only mode for lapsed Space tenants | pushed through `site_config` |

ERPNext stays the accounting and stock engine: zatgo_core posts through ERPNext's document controllers and never writes GL or stock ledger rows itself.

## Scale (at `d5bc17b`)
| | |
|---|---|
| Python | 916 files, about 90,000 lines (services 21.6k, tests 19.6k, chat_ai 17.9k, api 8.8k) |
| DocTypes | 84 (61 ZatGo Core, 16 Chat AI, 5 ZatGo Space, 2 Tracker); 59 carry the `ZG ` prefix |
| Whitelisted methods | 488 (6 `allow_guest`) |
| Tests | 120 files, 1,514 test functions |
| Patches | 52 in `patches.txt` (`[pre_model_sync]` / `[post_model_sync]`) |
| Docs | 31 Markdown files in `docs/` before this phase |

## Where things stand
- **Production** (Hetzner `2.29.17.8`): `1a0e621` deployed 2026-11-06 to accounting, democompanysa, kasibasia and testerp. Later deploys by other sessions are recorded in the workspace notes (11-16 print/mobile cards on all sites). **The exact commit now on each site was not checked for this document.**
- **`main`** is 6 commits ahead of `origin/main` (licensing phases 5 to 10, local only).
- **Branch `rename-zatgo`** (pushed) drops the `ZG` prefix from DocTypes, with migration patch `v0_6_0`. It runs live on `signxdemo`. **This is the chosen naming (ADR-005, 2026-11-28).** `licensing-phase10-on-rename` carries the same licensing work as `main`, so the rename line is the current code. Names in these documents are `main`'s (`ZG …`); each maps to its new name by dropping `ZG` (or `ZatGo <Name>` where ERPNext has the name, see ADR-005).
- **40 files are modified and 4 paths untracked** in the working tree. That is other sessions' unfinished work (Duplicate Prevention `v0_5_1`, Chat AI tool hints, VanSaleX settings, POS and delivery, theme tokens). None of it is part of this phase.

## Documents
| Phase | Document | Content |
|---|---|---|
| 0 | `PROJECT_OVERVIEW.md` | this page |
| 0 | `REPOSITORY_STRUCTURE.md` | folders, packaging, branches, working-tree state |
| 0 | `CURRENT_ARCHITECTURE.md` | how the app hooks into Frappe/ERPNext, settings, permissions, storage, upgrades |
| 0 | `EXISTING_FEATURES.md` | every feature: purpose, location, DocTypes, status, problems |
| 0 | `DEPENDENCY_MAP.md` | app, module, switch and ERPNext dependencies |
| 1 | `TECHNICAL_AUDIT.md`, `SECURITY_AUDIT.md`, `PERFORMANCE_AUDIT.md`, `COMPATIBILITY_AUDIT.md`, `IMPLEMENTATION_PLAN.md` | findings and the prioritized plan |
| 2 | `TARGET_ARCHITECTURE.md`, `ARCHITECTURE_DECISIONS.md`, `MODULE_DEPENDENCIES.md` | the proposed design, for validation |

The older topic docs (`architecture.md`, `folder_structure.md`, `doctypes.md`, `licensing.md`, `permissions.md`, ...) stay the detailed reference for their subject. Where they disagree with these documents, these are newer.
