# Repository structure

*Phase 0, 2026-11-28, `main` at `d5bc17b`.*

## Top level
| Path | Purpose |
|---|---|
| `zatgo_core/` | the Frappe app package |
| `docs/` | documentation (31 topic files plus these phase documents) |
| `scripts/` | build and maintenance scripts (`build_saas_theme.py`, `deploy_web_build.sh`, `self_hosted_ai/`, guarded generators) |
| `pyproject.toml`, `setup.py` | packaging; both say version **0.4.0** |
| `MANIFEST.in` | ships templates, public, translations, every JSON, `modules.txt`, `patches.txt` |
| `LICENSE` | MIT (2026, ZatGo Innovation) |
| `CLAUDE.md` | repo-specific working rules (about 20 KB) |
| no `requirements.txt` | dependencies live in `pyproject.toml` |

## Packaging and install
- `pyproject.toml`: `requires-python >=3.11`; dependencies `qrcode[pil]`, `anthropic>=1.0`, `pypdf>=4.0`, `python-docx>=1.1` (lower bounds only); `[tool.bench.frappe-dependencies]` pins `frappe >=16,<17` and `erpnext >=16,<17`.
- `hooks.py`: `required_apps = ["erpnext"]`, `before_install` refuses any Frappe/ERPNext major other than 16.
- Install from GitHub: `bench get-app https://github.com/teamzatgoinnovation-collab/zatgo-core` then `bench --site X install-app zatgo_core` (`docs/installation.md`).

## The app package (`zatgo_core/`)
Python lines per folder (excluding `__pycache__`):

| Folder | Lines | What lives there |
|---|---|---|
| `services/` | 21,607 | business logic: VanSaleX, POS, accounting writes/reads, payments, naming, print, ZATCA QR, app platform (catalog, state, gate, authority, sidebar, desk), subscription gate, `duplicate/`, `mybis/` |
| `tests/` | 19,639 | `integration/` (75 files), `unit/` (30), `api/`, `permissions/` |
| `chat_ai/` | 17,861 | ZatGo AI module: `core/` (providers, tools, local guard), `erpnext/` (orchestrator, tasks), `api/`, `doctype/`, `desk_records/`, `tests/` |
| `api/` | 8,795 | whitelisted endpoints, `api/v1/<domain>/` (accounting, vansalex, resto_pos, retail_pos, mybis, licensing, duplicate, delivery, fleet, gym, jewellery, crm, hr, service, warehouse, sync, portals, admin, bi, documentation) |
| `setup/` | 4,700 | idempotent install/migrate steps: custom fields, roles, perms, print formats, Desk records, deploy check |
| `licensing/` | 4,115 | editions, licences, registry `catalog/`, gate, issuer, audit |
| `tracker/` | 4,090 | Tracker module |
| `patches/` | 2,273 | `v0_1_0` … `v0_5_2` |
| `zatgo_core/` | 1,675 | the Frappe module folder: `doctype/`, `page/`, `report/`, `workspace/`, `print_format/`, `number_card/` |
| `zatgo_space/` | 990 | ZatGo Space module |
| `industries/` | 715 | registry, gate, sync, `gym/`, `jewellery/`, `restaurant/`, `textile/` |
| `events/` | 582 | doc-event handlers for ERPNext DocTypes |
| `plugins/` | 555 | catalog manifests (`manifests/core_apps.py`), registry projection (`discover.py`) |
| `constants/`, `validation/`, `overrides/`, `permissions/`, `mixins/`, `cache/`, `repositories/`, `utils/`, `config/`, `workflow/`, `www/`, `mybis/` | under 400 each | shared constants and roles, validators, class extensions and method overrides, permission hooks, mixins, cache wrapper, a thin repository layer, `/vansalex` page |
| `public/` | — | `js/` (form scripts, route redirects, mobile forms, subscription banner), `css/`, `saas_theme/` (CSS partials and build output, fonts), `chat_ai/`, `tracker/`, `language_switcher/`, `images/`, the VanSaleX web build |
| `templates/` | — | themed login page, ERP summary block |
| `translations/` | — | `ar.csv` (38 lines) |
| `print_formats/` | — | HTML sources used by `setup/ensure_print_formats.py` |

There is **no `fixtures/` folder**. `hooks.py` exports one fixture, Role, for 8 ZatGo roles. Everything else is created in code by `setup/` and `install.py`.

### Records shipped as files
| Kind | Count | Names |
|---|---|---|
| Workspaces (synced) | 8 | ZatGo, ZatGo ERP, ZatGo VanSaleX, ZatGo POS, ZatGo MyBis, ZatGo VanSaleX Web, ZatGo Desk Theme, ZatGo Language Switcher |
| Workspaces (made in code from `desk_records/`) | 3 | ZatGo AI, ZatGo Tracker, ZatGo Space |
| Pages | 6 | `zg_app_hub`, `zg_edition_builder`, `zg_licence`, `tracker_hours`, `tracker_org`, `tracker_workbench` |
| Reports | 2 | Business Summary Report, Payment Method Summary |
| Number Cards | 8 | ZatGo ERP dashboard |
| Print Formats | in code | VanSale Tax Invoice, ZatGo Quotation, A4/80mm Sales Invoice, Kasib Asia formats, report formats |
| Client Scripts, Server Scripts, Property Setter files, Custom Field files | 0 | made in code instead |

## Branches (2026-11-28)
| Branch | vs `main` | Note |
|---|---|---|
| `main` | — | HEAD `d5bc17b`, 6 ahead of `origin/main` |
| `rename-zatgo` | +4 / −1 | drops `ZG` from DocTypes; pushed; live on `signxdemo` |
| `licensing-phase10-on-rename` | +2 / −1 | licensing rebased on the rename |
| `release/pos-sessions-on-1a0e621` | +1 / −41 | deploy branch for POS cash sessions |
| `settings-map`, `deploy-settings-map` | +1 / −67, −69 | Settings Map page; its files are on the server but not in `main` |
| `saas-theme-modernization`, `saas-theme-crm-style` | +4 / −165, −90 | theme work, pushed, not merged |
| `deploy-*` (3) | +1–2 / −104 | old deploy branches |

## Working tree (not part of any commit)
40 modified files and 4 untracked paths (`patches/v0_5_1/`, `chat_ai/core/tool_hints.py`, `public/css/zg_components.css`, `public/images/`). `patches.txt` already lists `v0_5_1` and `v0_5_2`, so `patches.txt` and those patch folders must be committed together.
