# Performance audit

*Phase 1, 2026-11-28, `main` at `d5bc17b`. Nothing was measured on a running site for this document. Every item below is a candidate to **measure before changing** (Phase 12).*

The production box has 2 vCPU and 3.7 GB RAM, with swap in use and the disk at 95%. Many sites share one bench, so hook overhead is paid by every site.

## Findings
| ID | Sev | Where | Existing → problem | Risk | Recommendation | Prio |
|---|---|---|---|---|---|---|
| P-01 | MED | `hooks.py` `"*"` | 14 handlers on every document event of every DocType (subscription gate on 7 events, licence gate on 3, Chat AI on 4), plus 4 `has_permission` and 2 `permission_query_conditions` handlers on every permission check. | Each returns early when off, but every call still reads site_config, cached settings and licence state. On large list views and imports that is thousands of calls. | Measure with `frappe.recorder` on a Sales Invoice list and a 1,000-row import; memoise per request (`frappe.local`); register `"*"` handlers only for the feature in use, where Frappe allows. | P2 |
| P-02 | MED | `before_request` (4 hooks) | Run on every request, assets and guest pages included. | Latency per request. | Measure; skip non-API, non-Desk paths early. | P2 |
| P-03 | MED | Unbounded reads | 109 `frappe.get_all` calls in `services/` and `api/`; several without a limit (e.g. `vansalex/aging.py`, `returns.py`, `devices.py`, `kds_tickets.py`, `mybis/notify.py`); the accounting dashboard loads open invoices several times; `vansalex/admin.py` caps at 5,000 and gives wrong totals past it. | Memory and time grow with data; silent wrong totals. | Paginate APIs; aggregate in SQL for dashboards; report when a cap is hit. | P2 |
| P-04 | MED | `vansalex_settings.resolve()` | 20–40 queries, called 4–6 times per order (10-23 M16). | Slow van-sale posting. | Per-request cache keyed by user and company. | P2 |
| P-05 | LOW | Loops of `get_doc` | `resto_pos_service.py` (per name), `invoice_cash_payment_service.py` (full docs in a loop). | N+1. | Batch with `filters={"name": ["in", ...]}` and `pluck`. (Verified wrong on 11-06: `vansalex/orders.py` is already batched.) | P3 |
| P-06 | LOW | `after_migrate` | About 16 steps with several global `clear_cache()` calls; print formats re-rendered; Desk records rebuilt. | Slow migrates; the server was nearly out of memory during one (11-06). | Seed-once markers (T-11); clear cache once at the end. | P3 |
| P-07 | LOW | Indexes | 18 `search_index` and 23 `unique` fields across ZatGo DocTypes; filters on ZG Trip, `owner`, AI usage partly indexed (patches `v0_5_0`, 10-24). | Slow lists as data grows. | `EXPLAIN` the top list and report queries in Phase 12; add indexes by patch. | P3 |
| P-08 | LOW | Assets | Theme CSS about 238 KB un-minified (51 KB gzipped), loaded per request where the theme is on; VanSaleX web build is about 44 MB per build kept on the server. | First paint; server disk. | Minify in `build_saas_theme.py`; keep one web build. | P3 |

## Sound practice already in place
- Switch reads are cached (cached doc and a small dict).
- MyBis has a cache layer.
- Duplicate Prevention caps its fuzzy candidates and has indexes (`v0_5_0`).
- Statements and aging reuse ERPNext reports.
- Heavy setup is idempotent, so a re-run does no repeat writes.
