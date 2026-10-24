# MyBis API (`zatgo_core.api.v1.mybis.*`)

Read-only management dashboards for the MyBis Flutter app (`flutter/mybis`). Switch: ZG System Settings -> Apps -> *Enable ZatGo MyBis*
(`enable_mybis`, off by default; off = every method answers 404). ERPNext's ledgers stay the source of truth; nothing here writes.

## Request shape
Every endpoint takes `company`, `preset` (`today`..`last_year`, `custom`), `from_date`/`to_date` (custom only), `compare` (1/0), `refresh` (1 = bypass cache).
`company` must be one the caller may read (Company User Permission); none given = the user's default, else their only company, else an error -- never "all companies".
Responses use the standard envelope; `meta` carries `company`, `currency` (company currency), `period`, `previous_period`, `cached`, `cached_at`, `ttl`.
Presets and the comparison period are defined once, in `services/mybis/period.py` (`context.resolve_period` exposes them): this month compares with the previous calendar month, a custom range with the same number of days before it.

## Endpoints
| Method | Returns |
|---|---|
| `context.get_context` | user, readable companies + currency, `areas` (which sections the user's ERPNext permissions open), presets, server date |
| `context.resolve_period` | concrete dates of a preset and of its comparison period |
| `dashboard.kpis` | headline figures, each `{value, previous_value, change, growth_percent, higher_is_better}`; `{available:false}` when the caller may not read the source |
| `dashboard.sales_trend` | net sales per day / week / month (auto by range; `group_by` overrides), previous period alongside; empty buckets are 0; the future is not plotted |
| `dashboard.top_categories`, `dashboard.top_products` | ranked by net sales (`order=quantity` for products), with share of total and growth |

## Figure definitions (company currency, `base_*` fields, submitted documents only)
- **Total sales** = sum of `base_net_total` of non-return Sales Invoices (before tax). **Net sales** = total sales + returns (return invoices are negative). Discount, tax, invoice count, average order value are in `sales_detail`.
- **Purchases** = net of returns, Purchase Invoices, `base_net_total`.
- **Expenses** = GL debit-credit on Expense accounts that are not Cost of Goods Sold. **Net profit** = GL Income - COGS - expenses. Cancelled entries and Period Closing Vouchers are excluded.
- **Gross profit** = net sales - COGS, with `basis`: `gl` when the company has perpetual inventory (COGS from the ledger); `valuation_estimate` otherwise (Sales Invoice Item `incoming_rate` x `stock_qty` of stock items) -- the app labels it an estimate. `margin_percent` = gross profit / net sales.
- **Receivables / Payables** = GL balance of Receivable / Payable accounts as of the period's end (previous: as of the previous period's end). This is the ledger ERPNext's aging reports start from; use ERPNext's Accounts Receivable report for per-customer detail.
- **Stock value** = sum of Stock Ledger Entry `stock_value_difference` up to the period end.
- `growth_percent` is null when there is no base (previous = 0 or compare off); the app says "No comparison", never a made-up 0 or 100.

## Permissions and safety
`@frappe.whitelist` methods require a login, read permission on each source DocType (a figure whose source is not readable is `available:false`), and refuse users who carry **record-level User Permissions other than Company** (raw SQL cannot apply them to totals -- `queries.guard`). Aggregates are SQL (no row downloads); cache key = user + company + request, TTL 300 s.

Tests: `tests/unit/test_mybis_period.py`, `test_mybis_metrics.py`; `tests/integration/test_mybis_context.py`, `test_mybis_dashboard.py` (real invoices, a return, ledger reconciliation, company isolation, restricted users).
