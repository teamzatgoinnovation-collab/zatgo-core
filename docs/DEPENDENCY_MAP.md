# Dependency map

*Phase 0, 2026-11-28, `main` at `d5bc17b`.*

## Platform
| Layer | Dependency | Pinned by |
|---|---|---|
| Frappe | 16.x (local 16.29, production image 16.34.1) | `pyproject.toml` `[tool.bench.frappe-dependencies]`, `install.before_install` |
| ERPNext | 16.x (local 16.31) | same, plus `required_apps = ["erpnext"]` |
| Python | ≥ 3.11 (bench envs run 3.12/3.14) | `requires-python` |
| PyPI | `qrcode[pil]`, `anthropic>=1.0`, `pypdf>=4.0`, `python-docx>=1.1` | lower bounds only |
| Optional apps on the same bench | `hrms` (also extends Payment Entry; zatgo_core uses `extend_doctype_class` so both apply), `zatca_erpgulf` / `zatca_integration` (ZATCA Phase 2 QR), `print_designer` | not declared; detected at runtime where used |
| Services | Ollama or another local model server (ZatGo AI); SearXNG (search); ZatGo Space platform (pushes `zg_subscription`) | settings / site_config |

## Internal dependencies (Python packages)
```
api/v1/*  ──► services/* ──► ERPNext controllers / frappe ORM
   │            │
   │            ├─► services/app_state  (the only reader of ZG System Settings switches)
   │            ├─► services/row_scope, permissions/*, idempotency
   │            └─► licensing/entitlement (only when enforcement is on)
   ├─► services/app_gate (prefix → 404)   industries/gate   subscription_gate
hooks.py ──► events/*, services/*, overrides/*, licensing/gate, bundled_apps (gated wrappers for chat_ai, tracker, zatgo_space)
install.py ──► setup/* (idempotent steps) ──► patches/* (functions reused for self-healing)
licensing/catalog ──bridge──► app_catalog keys, industries registry, vansalex_access keys   (bridges only; those stay the truth)
```
Known layering exceptions: business logic inside `api/v1/delivery/stops.py` and parts of `vansalex/orders.py`, `vansalex/admin.py` and `resto_pos/kds_tickets.py`; `industries/gate` imports a private helper from `bundled_apps`.

## Three "is it available" systems
| System | Granularity | Stored in | Decides |
|---|---|---|---|
| App switches (`app_catalog` + `app_state`) | 13 apps + `requires` (e.g. `vansalex_web` requires `vansalex`) | ZG System Settings `enable_*` | API 404, sidebar, folder, hidden workspace |
| Industries | 5 verticals | ZG System Settings → Enabled Industries | industry API 404 and `"*"` permission hooks |
| Licensing registry | 19 modules, 115 features, 148 DocTypes, `requires` between features | code (`licensing/catalog`), projected to ZG Module / ZG Feature; signed licence | document actions (create/write/submit/...) when enforcement is on |

A ZatGo **module** today means a licensing module. A ZatGo **app** means a catalog entry with a switch. Phase 5 asks for "ZG Module Settings"; `MODULE_DEPENDENCIES.md` proposes building it on these instead of adding a fourth system.

## Licensing modules and their cross-module requirements
| Module | Requires features from |
|---|---|
| foundation | — (in every edition) |
| sales, procurement, inventory, accounting, tax | within themselves |
| pos | accounting, sales |
| hr_payroll | accounting |
| crm, production, quality, service | production (internal) |
| dashboard, reports, data_management, print | — |
| zatgo_apps, vansalex, industries | accounting, inventory, pos, procurement, sales, vansalex |

Gate Management is not registered (decision D7: nothing implements it).

## ERPNext APIs zatgo_core calls directly
`payment_entry.get_payment_entry` (12 call sites), `sales_and_purchase_return.make_return_doc` (8), `accounts_controller.get_taxes_and_charges`, `accounts.utils.get_fiscal_year` / `get_balance_on`, the `make_sales_invoice` mappers for Sales Order and Quotation, `customer.get_credit_limit` / `get_customer_outstanding`, `purchase_order.get_mapped_purchase_invoice`, `party.get_party_account`, `make_sales_return`, `make_debit_note`, `pos_closing_entry.make_closing_entry_from_opening`, and the `PaymentEntry` class (subclassed through `extend_doctype_class`). These are internal ERPNext functions, not a stable API. `COMPATIBILITY_AUDIT.md` covers the upgrade risk.
