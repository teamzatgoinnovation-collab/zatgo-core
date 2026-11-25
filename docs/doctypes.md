# DocTypes — ZatGo Core

Module: **ZatGo Core** (plus the bundled modules Chat AI, Tracker and ZatGo Space — see the full inventory at the end)

## Singles (global)

| DocType | Purpose |
|---------|---------|
| ZatGo System Settings | App switches, industries, ERP behaviour flags (IFRS, auto-fill, stock summary), maintenance. Its timezone / country / currency / date format / fiscal year / default company, warehouse and cost center fields repeat Frappe and ERPNext settings and are mostly unread; brand, logo, theme and language moved to ZatGo Theme / Language Settings |
| Integration Settings | WhatsApp, SMS, Email, Firebase, Maps, AI providers, OAuth/JWT, webhooks |
| Printer Settings | Receipt / kitchen / barcode / label / A4, margins, auto/silent print |
| Payment Settings | Cash/card/bank/wallet/gift card, split, tips, service charge, round-off (stored; no code reads it yet, the modes of payment themselves are ERPNext's) |
| ZatGo Notification Settings | Desktop, push, email, SMS, WhatsApp, Telegram, Slack, in-app |
| Storage Settings | Local/S3/R2/Drive/Dropbox/Azure + backup retention |
| ZatGo Security Settings | Password policy, OTP/2FA, session, IP/devices, audit, API keys (validated only, not applied: Frappe's System Settings is what enforces them) |
| Sync Settings | Offline mode, interval, retry, conflict strategy, Redis queue |
| Number Series Settings | Child table of prefixes/sequences for all document types (seeded and validated, **not applied**: numbering is Frappe's Series / Document Naming Settings, and Sales Invoice Naming Settings for per-user invoice series) |
| Sales Invoice Naming Settings | User-wise Sales Invoice naming: (user, company) → invoice series + return series, and what happens to users without a rule. Enforced in the Sales Invoice `before_insert` hook by `services/sales_invoice_naming.py` for every entry point (desk, REST, VanSaleX API, Create Return) |

## List DocTypes

| DocType | Key | Purpose |
|---------|-----|---------|
| Company Settings | `company` (unique) | Tax, accounting, inventory, sales, purchase, POS, branding |
| Branch Settings | autoname `BR-{company}-{#####}` | Warehouse, POS, printers, shift, delivery zone |
| Application Settings | Single | Site settings for Electron / Flutter / Web clients
| Client Application | child | One client product row (app_key, platform, enabled) |
| Feature Flag | `flag_key` | Enable/Disable/Experimental/Hidden/Internal/Beta |
| User Preferences | `user` | Theme, sidebar, language, landing page, favorites |
| Audit Log | `AUD-.YYYY.-.#####` | Old/new value, actor, IP, browser, reason, app |
| Number Series Item | child table | Document type + prefix + format + current value |

## Child tables

- `Number Series Item` → parent `Number Series Settings.series_items`
- `Sales Invoice Naming Rule` → parent `Sales Invoice Naming Settings.rules` (one row per user + company)
- `ZatGo Mode of Payment Account` → parent `Mode of Payment.custom_zg_accounts` (allowed ledger accounts per payment method + company; see `multi_payment.md`)
- `Payment Allocation` → parent `Payment Entry.custom_payment_details` (payment split across methods / accounts; see `multi_payment.md`)

## Why not literal "System Settings"?

Frappe already ships `System Settings`. Using `ZG *` keeps the ecosystem safe on
shared sites and makes ownership obvious in Desk search.

## Full inventory (68 DocTypes)

Generated from the DocType JSON on 2026-10-23. `ZG …` is the naming standard (`naming.md`); the other 25 are
legacy names that are kept on purpose. Field counts exclude layout breaks.

| Module | DocType | Kind | Fields |
|---|---|---|---|
| ZatGo Core | VanSaleX Access | Child table | 6 |
| ZatGo Core | VanSaleX Settings | Single | 14 |
| ZatGo Core | Application Registry | List | 15 |
| ZatGo Core | Application Settings | Single | 6 |
| ZatGo Core | Audit Log | List | 12 |
| ZatGo Core | Branch Settings | List | 16 |
| ZatGo Core | Client Application | Child table | 12 |
| ZatGo Core | Company Settings | List | 28 |
| ZatGo Core | Config History | List | 8 |
| ZatGo Core | Config Profile | List | 5 |
| ZatGo Core | Delivery Boy | List | 12 |
| ZatGo Core | ZatGo Delivery Stop | List | 31 |
| ZatGo Core | Device Token | List | 5 |
| ZatGo Core | Enabled Industry | Child table | 5 |
| ZatGo Core | Feature Flag | List | 9 |
| ZatGo Core | Gym Attendance | List | 4 |
| ZatGo Core | Gym Membership | List | 11 |
| ZatGo Core | Gym Plan | List | 5 |
| ZatGo Core | Integration Settings | Single | 31 |
| ZatGo Core | KDS Ticket | List | 11 |
| ZatGo Core | Metal Rate | List | 4 |
| ZatGo Core | ZatGo Mode of Payment Account | Child table | 5 |
| ZatGo Core | ZatGo Notification Settings | Single | 12 |
| ZatGo Core | Number Series Item | Child table | 6 |
| ZatGo Core | Number Series Settings | Single | 1 |
| ZatGo Core | Order | List | 24 |
| ZatGo Core | Order Item | Child table | 8 |
| ZatGo Core | Payment Allocation | Child table | 7 |
| ZatGo Core | Payment Settings | Single | 13 |
| ZatGo Core | Printer Settings | Single | 14 |
| ZatGo Core | Registered Application | List | 13 |
| ZatGo Core | Sales Invoice Naming Rule | Child table | 5 |
| ZatGo Core | Sales Invoice Naming Settings | Single | 2 |
| ZatGo Core | ZatGo Security Settings | Single | 15 |
| ZatGo Core | Service Ticket | List | 8 |
| ZatGo Core | Setting Section | List | 13 |
| ZatGo Core | Storage Settings | Single | 19 |
| ZatGo Core | Sync Settings | Single | 7 |
| ZatGo Core | ZatGo System Settings | Single | 30 |
| ZatGo Core | Table | List | 8 |
| ZatGo Core | Trip | List | 18 |
| ZatGo Core | User Preferences | List | 9 |
| ZatGo Core | Van Sale Profile | List | 18 |
| ZatGo Core | Van Sale Profile Access | Child table | 2 |
| ZatGo Core | ZatGo Vehicle | List | 5 |
| Chat AI | AI Artifact | List | 8 |
| Chat AI | AI Attachment | List | 11 |
| Chat AI | AI Chat Memory | List | 4 |
| Chat AI | AI Chat Message | List | 14 |
| Chat AI | AI Chat Session | List | 8 |
| Chat AI | AI Conversation Summary | List | 3 |
| Chat AI | AI Integration Connector | List | 16 |
| Chat AI | AI MCP Server | List | 13 |
| Chat AI | AI Plugin Registry | List | 6 |
| Chat AI | AI Provider Health Log | List | 6 |
| Chat AI | AI REST Tool | List | 16 |
| Chat AI | AI Scheduled Task | List | 18 |
| Chat AI | AI Search Index | List | 12 |
| Chat AI | AI Tool Log | List | 11 |
| Chat AI | AI Usage Daily | List | 10 |
| Chat AI | Chat AI Settings | Single | 89 |
| Tracker | Tracker Activity Session | List | 13 |
| Tracker | Tracker Settings | Single | 2 |
| ZatGo Space | Space Job Log | List | 6 |
| ZatGo Space | Space Order | List | 14 |
| ZatGo Space | Space Order App | Child table | 2 |
| ZatGo Space | Space Plan | List | 8 |
| ZatGo Space | Space Settings | Single | 2 |
