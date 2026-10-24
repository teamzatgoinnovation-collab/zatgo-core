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
| `sales.breakdown_by`, `purchase.breakdown_by` | ranked rows by `customer`/`supplier`, `product`, `category`, `warehouse` (sales also `salesperson`); a `filters` JSON narrows by one value per drill step; rows carry share, growth and (sales) estimated profit. `order` = `revenue` (default) / `quantity` / `profit` (sales) / `growth` -- see Analytics definitions |
| `sales.movers`, `purchase.movers` | what changed against the previous period for one `dimension`: the `limit` (default 5, max 20) biggest gains and declines, each with revenue now, before, change, growth and `status` (`new` / `lost` / `changed`), plus `net_change`, `growth_percent`, `gains_total`, `declines_total` (gains + declines = net change) |
| `sales.invoices`, `purchase.invoices` | paginated invoices behind a figure (same `filters`), newest first |
| `sales.invoice_detail`, `purchase.invoice_detail` | one invoice with items and totals (ERPNext read permission + company restriction) |
| `inventory.summary` | stock value / quantity, alert counts, idle-days buckets, turnover and the explained health score |
| `inventory.alerts` | paginated rows for `low_stock`, `out_of_stock`, `negative`, `slow_moving`, `never_sold`, `overstock`, `fast_moving` |
| `finance.summary` | revenue, COGS, gross / net profit, expenses (General Ledger) and cash, bank, receivables, payables as of the period's end (today, for a period that has not ended) |
| `finance.trends` | 12 monthly points up to the period's end: revenue, expenses, net profit, month-end receivables, payables, cash + bank |
| `finance.profit_and_loss`, `finance.balance_sheet`, `finance.cash_flow` | **ERPNext's own reports** (`erpnext.accounts.report.*`), rows reshaped (`group` / `account` / `total`), with the previous period merged in; requires permission on the Report |
| `finance.aging(kind=receivable\|payable)` | ERPNext's Accounts Receivable / Payable *Summary*: totals per bucket (Not due, 0-30, 31-60, 61-90, 90+) and parties, most overdue first |
| `finance.party_invoices` | the open items behind one party's aging row (ERPNext's detailed Accounts Receivable / Payable report); invoices link to `*.invoice_detail` |
| `parties.summary(kind=customer\|supplier)` | active, new (first-ever invoice in the period), returning, with a balance, total outstanding, overdue |
| `parties.ranking(kind, order)` | customers by `revenue` / `profit` / `orders` / `outstanding`; suppliers by `revenue` (spend) / `orders` / `outstanding`; each row has outstanding + overdue. A party's own drill-down is `sales.breakdown_by` / `purchase.breakdown_by` with `filters={"customer": ...}` |
| `forecast.project(subject, horizon, method)` | statistical forecast of `sales` / `revenue` / `purchases` / `cash_flow` / `customer` (+`party`) for `7d` / `30d` / `90d` / `12m`: history, forecast with likely range, summary (historical total vs forecast total and change), method, confidence, limitations; cash flow adds the projected balance and the invoices falling due |
| `forecast.demand` | per stock item: 90-day sales, forecast demand, stock, on order, suggested reorder = max(0, demand - stock - on order), days of cover. Informational: no purchase order is created |
| `forecast.methods` | the methods, horizons and subjects the app can offer |
| `alerts.feed` | all alerts (risks) and insights (observations) for the period, most severe first, each with metric, values, source, calculation, underlying data and a `drill` target |
| `alerts.summary` | counts by severity / type and the three most severe items |
| `reports.catalog` | the 19 reports in four groups (Sales, Purchases, Inventory, Finance), whether each is ERPNext's own or a MyBis aggregate, its allowed filters and whether the caller may run it |
| `reports.run(report, ..., filters, page, page_size)` | one report as typed columns (`text` / `date` / `currency` / `number` / `percent`) and a page of rows, plus `total_rows`, totals and notes; cached 5 minutes like the screens |
| `reports.export(report, format=csv\|xlsx\|pdf, ...)` | the whole table generated on the server and returned base64-encoded with its file name; always computed fresh |
| `search.query(q, types, limit, company)` | customers, suppliers, items, sales / purchase invoices, payment entries, employees, warehouses matching `q` (2+ characters), each with a `drill` target; ERPNext permissions apply, unreadable types are listed in `skipped` |
| `search.record(type, name)` | key facts of a payment entry, employee or warehouse (the hits that have no screen of their own) |

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
- `order=growth` ranks by growth against the previous period **among the 100 biggest rows by revenue of this period** (`ranked_among` says how many it looked at), so a tiny item going from one sale to three does not top the list. Rows with nothing in the previous period have no growth and are left out; the request needs the comparison (`compare=1`), otherwise it is refused.
- Movers (`breakdown.movers`) look at up to 5,000 rows per period for the dimension; a row present in only one period is `new` (no previous revenue) or `lost` (no revenue now) and has no growth percentage. Purchases use the same endpoint: an increase there is spending up, which the app words and colours accordingly.
- Profit per row (sales) = revenue - valuation cost of stock items sold (`incoming_rate` x `stock_qty`), shown as an estimate.
- Inventory (`services/mybis/inventory.py`): stocked item = enabled stock Item with a Bin in the company's warehouses; out of stock = balance exactly 0; negative = any warehouse balance < 0; low stock = Bin at/below its Item Reorder level; slow-moving/dead = balance > 0 and no outward Stock Ledger Entry for 90 days; never sold = balance > 0 and no outward Stock Ledger Entry at all (a subset of slow-moving: nothing has ever left, by sale, issue or transfer); overstock = balance covers > 180 days at the last 90 days' outward rate; idle-days buckets = stock value by days since last outward movement (not FIFO batch aging); turnover = sales/delivery outward value over 90 days, annualised, over current stock value.
- Health score (0-100, `services/mybis/health.py`): availability 25, low stock 15, negative stock 15 (each negative item weighs 5x), dead stock 20, overstock 10, turnover 15 (full points at 4 turns a year). Every factor returns its points and a plain-language reason; no stock records = no score.

## Finance definitions
- The statements are not recomputed: the P&L, Balance Sheet and Cash Flow rows are ERPNext's report output, and the integration tests assert that the P&L's Net Profit equals the ledger-based KPI. The balance sheet is a position (as of the period's end, or today for an unfinished period) using the fiscal year of that date; a period outside any Fiscal Year gets ERPNext's own error message.
- Aging buckets are ERPNext's `range0..range5` (ageing based on Due Date): *Not due* = `<0`, `0-30`, `31-60`, `61-90`, `90+` = `91-120` + `121-Above`. Their sum equals the party's outstanding.
- Customers: *active* = distinct customers with a non-return invoice in the period; *new* = first-ever non-return invoice with this company falls in the period; *returning* = active - new.
- A cash-flow figure is only as meaningful as the chart: ERPNext derives it from Cash / Bank accounts, so a site that posts no payments shows zeros there.

## Forecasting methodology (`services/mybis/forecast.py`, `forecasting.py`)
This is classical time-series arithmetic over ERPNext history, **not machine learning**, and every response and screen says so ("Forecast (statistical estimate, not AI)"). History, forecast and estimate are separate series; a forecast never appears without its method, range and confidence.
- **Engines** (one `ForecastEngine` interface, so a learned model can be added later): moving average (last 7 days / 3 months), weighted moving average (newer points weigh more), simple exponential smoothing (alpha tuned on one-step error), Holt's linear trend (alpha, beta tuned). `method=auto` backtests all four on the last 30 points and takes the one with the lowest weighted absolute error.
- **Seasonality**: multiplicative weekday indices (daily series) or month indices (monthly) are applied only with at least two full cycles of history and a non-negligible pattern; otherwise the response says none was applied.
- **Likely range** (about 80%): the model's recent one-step error (RMSE) widened with the horizon by the standard exponential-smoothing variance formulas; sales-type subjects are floored at 0, cash movement is not.
- **Confidence** (high / medium / low) from the amount of history and the backtest error; any series with fewer than 7 points (6 months for the 12-month view) returns `available: false` with the reason instead of a number.
- **History window**: complete days / months only (today's partial figures are excluded); leading periods before the first activity are dropped and the response says so. Subjects: net sales and net purchases (invoices), revenue and cash movement (General Ledger, Cash/Bank accounts), a single customer's net sales, and per-item stock demand.
- **Cash flow**: projected balance = cash + bank today + cumulative forecast net movement; open invoices falling due in the window are shown separately as known items, not added to the forecast.
- **Limitations stated to the user**: it extrapolates the past and cannot anticipate promotions, price changes, new customers or holidays; fewer than 28 points, many empty periods, high volatility and long horizons each add an explicit warning.

## Insights and alerts (`services/mybis/insights.py`)
Rules over real figures, each producing: `id` (stable), `type` (alert = a risk that calls for action, insight = an observation), `severity` (critical / high / medium / low by the thresholds at the top of the module), the metric with current / previous value and change, `source`, a plain-text `calculation`, the underlying `data` rows and a `drill` target (`screen`, optional `tab` / `party` / `dimension` + `filters` / `kind`) that the app turns into navigation. A rule whose source the user cannot read is skipped (`skipped_rules`), never guessed.
Rules: net sales decline / growth, net loss / profit decline, gross-margin change, expense growth, top and fast-moving categories and products, top-customer share and concentration, receivables growth / overdue share / most overdue customer, payables overdue, cash not covering payables due in 30 days, out-of-stock / low / negative / dead stock, poor inventory health, stock value up while sales are flat. Growth needs a non-zero previous value: nothing is said from a base of 0.
**Like for like**: while the period has not ended (this month so far) the previous period is cut to the same number of days, and the response says so (`comparison_note`); a finished period is compared whole.
**Notifications**: the engine is pure and transport-free. `fingerprint` (id + company + severity + period start) is stable while a condition persists, so a later scheduled job can diff two runs and push only new or escalated items; no push is sent today.

## Reports and exports (`services/mybis/reports.py`)
- **Sources.** Profit & Loss, Balance Sheet, Cash Flow, Accounts Receivable / Payable, General Ledger, Stock Summary (Stock Balance), Stock Movement (Stock Ledger) and Stock Aging run ERPNext's own `execute()`; the caller needs ERPNext permission on that Report (`Report.is_permitted`). Sales / purchase summaries and breakdowns, slow- and fast-moving stock are MyBis aggregates, so a report and its screen agree. Nothing is recomputed in the reshaping step: ERPNext columns are typed, hidden ones dropped, ERPNext's display quoting (`'Opening'`) removed.
- **Limits.** A run or export carries at most 10,000 rows (the table says when it was cut); PDF at most 2,000; a file over 15 MB is refused. Filters are an allow-list per report (`account`, `party`, `party_type`, `voucher_no`, `item_code`, `warehouse`, `item_group`); anything else is a validation error.
- **Formats.** CSV is UTF-8 with a BOM so Excel reads Arabic; XLSX comes from Frappe's openpyxl helper with numbers as numbers; PDF is wkhtmltopdf through Frappe (landscape above 6 columns). All three render the same table and include the report title, company, period, currency and the time it was generated.
- **Spreadsheet formula injection.** Any text cell that starts with `=`, `+`, `-` or `@` is written with a leading apostrophe in CSV and XLSX, so a customer named `=HYPERLINK(...)` cannot run in the reader's spreadsheet.
- **Fresh exports.** `reports.export` never reads the five-minute screen cache.
- **Not in the report set.** Salesperson targets (ERPNext's Sales Person targets are not read), so "Salesperson Performance" shows net sales per salesperson only and says so in its notes.

## Search (`services/mybis/search.py`)
`frappe.get_list` per record type, so ERPNext and User Permissions apply to every hit; a type the caller may not read is skipped and reported. Hits are ranked exact > prefix > contains, limited per type, and a company filter applies to the types that carry one. The app debounces typing and opens a hit through the same drill router as an alert.

## Notifications (`services/mybis/notifications.py`)
The engine stays transport-free. `unread(items, seen)` returns items whose fingerprint (or short `sid`) the caller has not seen; a severity change is a new fingerprint, so "new or worse" is a set difference. `alerts.feed` accepts `seen` (JSON list of `sid`s) and `min_severity` and returns `unread`; the app keeps the seen list on the device and shows a badge. `NotificationChannel` / `dispatch` are the extension point for a future scheduled push or e-mail job; only the in-app channel exists today.

## Offline behaviour (app side)
Successful reads are copied to secure storage on the device (most recent 40, 400 KB each, per signed-in identity). When the server cannot be reached the saved copy is shown under an **Offline - showing data saved ...** banner with the age of the oldest figure; a server error, an expired session or an empty cache is never disguised as "offline". Exports, search and record summaries are never served from the copy ("This feature requires an internet connection"). The copy is removed on sign-out, when the session expires, from Settings, and when the setting is switched off. Trade-off: a copy of recent financial figures exists on the device until then.

## Permissions and safety
`@frappe.whitelist` methods require a login, read permission on each source DocType (a figure whose source is not readable is `available:false`), and refuse users who carry **record-level User Permissions other than Company** (raw SQL cannot apply them to totals -- `queries.guard`). Aggregates are SQL (no row downloads); cache key = user + company + request, TTL 300 s.

A user who may not read Company at all gets an empty `get_context` (`has_access: false`, the app shows its no-access screen), not an error. Every endpoint is discovered from the package by `tests/integration/test_mybis_security.py`, which checks that it refuses a Guest, is GET/POST only, refuses a user with no rights, and answers 404 through the app gate when the switch is off -- a new whitelisted function is covered without editing the test, and one that forgets `require_login` fails it.

SQL: statements are assembled from fixed fragments (column lists, join conditions, the item / party table of a side); a request value is only ever a bound parameter. `tests/unit/test_mybis_sql_safety.py` keeps the list of every text interpolated into SQL (each reviewed) and fails when a new one appears, when SQL text is built with `%` or `.format`, or when an endpoint module contains SQL of its own.

Tests: `tests/unit/test_mybis_period.py`, `test_mybis_metrics.py`, `test_mybis_health.py`, `test_mybis_forecast.py`, `test_mybis_sql_safety.py`; `tests/integration/test_mybis_context.py`, `test_mybis_dashboard.py` (real invoices, a return, ledger reconciliation, company isolation, restricted users), `test_mybis_analytics.py`, `test_mybis_finance.py`, `test_mybis_insights.py`, `test_mybis_reports.py`, `test_mybis_security.py`.
