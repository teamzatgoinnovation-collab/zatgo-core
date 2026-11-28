# Database architecture

*Phase 4, 2026-11-28, `main` after the `v0_6_0` rename. The per-DocType detail is in `DOCTYPE_CATALOG.md`.*

## What is stored where
| Data | Stored in | Authoritative? |
|---|---|---|
| Accounting (GL), stock (SLE, Bin), invoices, payments, orders, masters | ERPNext's own tables | **yes**, ERPNext is the system of record (ADR-001) |
| ZatGo fields on ERPNext documents | Custom Fields (`zatgo_client_id`, `zg_*`, `custom_*`, `vansale_*`) created in code by `setup/ensure_custom_fields.py` | yes, for what they hold (client id, narration, print values) |
| Settings | 20 Single DocTypes (rows in `tabSingles`) and per-company/branch/user DocTypes (Company Settings, Branch Settings, Van Sale Profile, Sales Invoice Naming Settings) | yes |
| ZatGo transactions that are not accounting | Trip, Order (+ Item), Table, KDS Ticket, ZatGo Delivery Stop, Delivery Boy, Service Ticket, Gym Membership/Attendance, Space Order | yes; money still posts through ERPNext documents (a paid Order links its Sales Invoice) |
| Registries projected from code | Module, Feature (licensing), Registered Application, Setting Section | **no**: rebuilt from code on migrate, read-only |
| Logs | Audit Log (append-only), Config History, Duplicate Override Log, Licence History, Offline Sale Issue, AI logs, Space Job Log | yes (evidence); never edited |
| Signed licences | Licence (the signed payload + hash); the entitlement is rebuilt from the signature | the signature is |
| Secrets | Password fields; `site_config` keys (`zg_subscription`, `zg_licence_*`, `space_internal_token`) | — |

## Keys and constraints
- **Idempotency**: `zatgo_client_id` has a **database UNIQUE index** on every DocType that takes client-created records (Sales Invoice, Payment Entry, Stock Entry, Sales Order, Purchase Invoice/Order, Journal Entry, Quotation, Customer, Item, Supplier, Warehouse, Address, Contact, Trip; Order and Offline Sale Issue in their JSON). Checked locally on 2026-11-06 with `information_schema`; production checked the same day.
- **22 unique fields** in ZatGo DocTypes: `module_id`, `feature_id`, `edition_id`, `payload_hash`, `code`, `token`, `user` on per-user records, `company` on Company Settings, and so on (catalog).
- **Duplicate Prevention** never adds unique keys on ERPNext columns. It uses a `validate` hook and the indexes from `v0_5_0`.
- **18 search indexes**. More come only after `EXPLAIN` on real queries (Phase 12).

## Naming
- Regular DocTypes name by field (`field:module_id`), by naming series, or by hash for logs and AI tables.
- Sales Invoice series per user come from Sales Invoice Naming Settings through the `before_insert` hook; a service never chooses `naming_series`.
- DocType names: plain, or `ZatGo <Name>` where Frappe/ERPNext has the name (ADR-005).

## Integrity tooling
`zatgo_core.setup.data_integrity.report` is read-only. Run it with `bench --site X execute zatgo_core.setup.data_integrity.report`. It reports, for every non-single ZatGo DocType:
- rows
- mandatory fields left empty
- Link values pointing at missing records
- duplicates in unique fields and `zatgo_client_id`
- orphaned child rows

Run it before and after every migration and compare. The rename rehearsal in `MIGRATION_PLAN.md` depends on it.

## Known weak points
| Point | Risk | Plan |
|---|---|---|
| 12 non-child DocTypes without version history | mostly logs and projections, which is correct; `AI Scheduled Task` and `Device Token` changes are untraced | turn on `track_changes` for AI Scheduled Task (Phase 12) |
| Generic DocType names (`Order`, `Table`, `Trip`, `Module`, `Feature`, `Licence`) | collision with another app's DocType | install/migrate name-collision guard (Phase 14) |
| Custom fields carry several historical prefixes | inconsistent, but renaming breaks clients and data | keep; new fields use `zg_` |
| Raw SQL for reports (MyBis, Business Summary) | bypasses User Permissions | `row_scope`, and MyBis refuses restricted users (S-08) |
