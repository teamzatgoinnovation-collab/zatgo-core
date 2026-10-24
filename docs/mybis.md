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
| `sales.summary`, `purchase.summary` | Sales / Purchases header figures with previous period (paid vs credit sales; outstanding payables from the ledger) |
| `sales.breakdown_by`, `purchase.breakdown_by` | ranked rows by `customer`/`supplier`, `product`, `category`, `warehouse` (sales also `salesperson`); a `filters` JSON narrows by one value per drill step; rows carry share, growth and (sales) estimated profit |
| `sales.invoices`, `purchase.invoices` | paginated invoices behind a figure (same `filters`), newest first |
| `sales.invoice_detail`, `purchase.invoice_detail` | one invoice with items and totals (ERPNext read permission + company restriction) |
| `inventory.summary` | stock value / quantity, alert counts, idle-days buckets, turnover and the explained health score |
| `inventory.alerts` | paginated rows for `low_stock`, `out_of_stock`, `negative`, `slow_moving`, `overstock`, `fast_moving` |
| `finance.summary` | revenue, COGS, gross / net profit, expenses (General Ledger) and cash, bank, receivables, payables as of the period's end (today, for a period that has not ended) |
| `finance.trends` | 12 monthly points up to the period's end: revenue, expenses, net profit, month-end receivables, payables, cash + bank |
| `finance.profit_and_loss`, `finance.balance_sheet`, `finance.cash_flow` | **ERPNext's own reports** (`erpnext.accounts.report.*`), rows reshaped (`group` / `account` / `total`), with the previous period merged in; requires permission on the Report |
| `finance.aging(kind=receivable\|payable)` | ERPNext's Accounts Receivable / Payable *Summary*: totals per bucket (Not due, 0-30, 31-60, 61-90, 90+) and parties, most overdue first |
| `finance.party_invoices` | the open items behind one party's aging row (ERPNext's detailed Accounts Receivable / Payable report); invoices link to `*.invoice_detail` |
| `parties.summary(kind=customer\|supplier)` | active, new (first-ever invoice in the period), returning, with a balance, total outstanding, overdue |
| `parties.ranking(kind, order)` | customers by `revenue` / `profit` / `orders` / `outstanding`; suppliers by `revenue` (spend) / `orders` / `outstanding`; each row has outstanding + overdue. A party's own drill-down is `sales.breakdown_by` / `purchase.breakdown_by` with `filters={"customer": ...}` |

## Figure definitions (company currency, `base_*` fields, submitted documents only)
- **Total sales** = sum of `base_net_total` of non-return Sales Invoices (before tax). **Net sales** = total sales + returns (return invoices are negative). Discount, tax, invoice count, average order value are in `sales_detail`.
- **Purchases** = net of returns, Purchase Invoices, `base_net_total`.
- **Expenses** = GL debit-credit on Expense accounts that are not Cost of Goods Sold. **Net profit** = GL Income - COGS - expenses. Cancelled entries and Period Closing Vouchers are excluded.
- **Gross profit** = net sales - COGS, with `basis`: `gl` when the company has perpetual inventory (COGS from the ledger); `valuation_estimate` otherwise (Sales Invoice Item `incoming_rate` x `stock_qty` of stock items) -- the app labels it an estimate. `margin_percent` = gross profit / net sales.
- **Receivables / Payables** = GL balance of Receivable / Payable accounts as of the period's end (previous: as of the previous period's end). This is the ledger ERPNext's aging reports start from; use ERPNext's Accounts Receivable report for per-customer detail.
- **Stock value** = sum of Stock Ledger Entry `stock_value_difference` up to the period end.
- `growth_percent` is null when there is no base (previous = 0 or compare off); the app says "No comparison", never a made-up 0 or 100.

## Analytics definitions
- Breakdown revenue = item rows' `base_net_amount` (company currency, before tax, returns negative), so a category's figure nets its returns; rows with zero net revenue are not listed. Salesperson revenue = invoice net total x the Sales Team's allocated percentage (no item-level filters).
- Drill-down: each step adds one filter (`category` -> `product` -> `customer` ...) until every dimension is fixed, then the invoice list and invoice detail. Dimension and filter names are an allow-list mapped to fixed SQL; client values are bound parameters only.
- Profit per row (sales) = revenue - valuation cost of stock items sold (`incoming_rate` x `stock_qty`), shown as an estimate.
- Inventory (`services/mybis/inventory.py`): stocked item = enabled stock Item with a Bin in the company's warehouses; out of stock = balance exactly 0; negative = any warehouse balance < 0; low stock = Bin at/below its Item Reorder level; slow-moving/dead = balance > 0 and no outward Stock Ledger Entry for 90 days; overstock = balance covers > 180 days at the last 90 days' outward rate; idle-days buckets = stock value by days since last outward movement (not FIFO batch aging); turnover = sales/delivery outward value over 90 days, annualised, over current stock value.
- Health score (0-100, `services/mybis/health.py`): availability 25, low stock 15, negative stock 15 (each negative item weighs 5x), dead stock 20, overstock 10, turnover 15 (full points at 4 turns a year). Every factor returns its points and a plain-language reason; no stock records = no score.

## Finance definitions
- The statements are not recomputed: the P&L, Balance Sheet and Cash Flow rows are ERPNext's report output, and the integration tests assert that the P&L's Net Profit equals the ledger-based KPI. The balance sheet is a position (as of the period's end, or today for an unfinished period) using the fiscal year of that date; a period outside any Fiscal Year gets ERPNext's own error message.
- Aging buckets are ERPNext's `range0..range5` (ageing based on Due Date): *Not due* = `<0`, `0-30`, `31-60`, `61-90`, `90+` = `91-120` + `121-Above`. Their sum equals the party's outstanding.
- Customers: *active* = distinct customers with a non-return invoice in the period; *new* = first-ever non-return invoice with this company falls in the period; *returning* = active - new.
- A cash-flow figure is only as meaningful as the chart: ERPNext derives it from Cash / Bank accounts, so a site that posts no payments shows zeros there.

## Permissions and safety
`@frappe.whitelist` methods require a login, read permission on each source DocType (a figure whose source is not readable is `available:false`), and refuse users who carry **record-level User Permissions other than Company** (raw SQL cannot apply them to totals -- `queries.guard`). Aggregates are SQL (no row downloads); cache key = user + company + request, TTL 300 s.

Tests: `tests/unit/test_mybis_period.py`, `test_mybis_metrics.py`; `tests/integration/test_mybis_context.py`, `test_mybis_dashboard.py` (real invoices, a return, ledger reconciliation, company isolation, restricted users).
