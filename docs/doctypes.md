# DocTypes — ZatGo Core

Module: **ZatGo Core** (plus the bundled modules Chat AI, Tracker and ZatGo Space — see the full inventory at the end)

## Singles (global)

| DocType | Purpose |
|---------|---------|
| ZG System Settings | App switches, industries, ERP behaviour flags (IFRS, auto-fill, stock summary), maintenance. Its timezone / country / currency / date format / fiscal year / default company, warehouse and cost center fields repeat Frappe and ERPNext settings and are mostly unread; brand, logo, theme and language moved to ZG Theme / Language Settings |
| ZG Integration Settings | WhatsApp, SMS, Email, Firebase, Maps, AI providers, OAuth/JWT, webhooks |
| ZG Printer Settings | Receipt / kitchen / barcode / label / A4, margins, auto/silent print |
| ZG Payment Settings | Cash/card/bank/wallet/gift card, split, tips, service charge, round-off (stored; no code reads it yet, the modes of payment themselves are ERPNext's) |
| ZG Notification Settings | Desktop, push, email, SMS, WhatsApp, Telegram, Slack, in-app |
| ZG Storage Settings | Local/S3/R2/Drive/Dropbox/Azure + backup retention |
| ZG Security Settings | Password policy, OTP/2FA, session, IP/devices, audit, API keys (validated only, not applied: Frappe's System Settings is what enforces them) |
| ZG Sync Settings | Offline mode, interval, retry, conflict strategy, Redis queue |
| ZG Number Series Settings | Child table of prefixes/sequences for all document types (seeded and validated, **not applied**: numbering is Frappe's Series / Document Naming Settings, and ZG Sales Invoice Naming Settings for per-user invoice series) |
| ZG Sales Invoice Naming Settings | User-wise Sales Invoice naming: (user, company) → invoice series + return series, and what happens to users without a rule. Enforced in the Sales Invoice `before_insert` hook by `services/sales_invoice_naming.py` for every entry point (desk, REST, VanSaleX API, Create Return) |

## List DocTypes

| DocType | Key | Purpose |
|---------|-----|---------|
| ZG Company Settings | `company` (unique) | Tax, accounting, inventory, sales, purchase, POS, branding |
| ZG Branch Settings | autoname `BR-{company}-{#####}` | Warehouse, POS, printers, shift, delivery zone |
| ZG Application Settings | Single | Site settings for Electron / Flutter / Web clients
| ZG Client Application | child | One client product row (app_key, platform, enabled) |
| ZG Feature Flag | `flag_key` | Enable/Disable/Experimental/Hidden/Internal/Beta |
| ZG User Preferences | `user` | Theme, sidebar, language, landing page, favorites |
| ZG Audit Log | `AUD-.YYYY.-.#####` | Old/new value, actor, IP, browser, reason, app |
| ZG Number Series Item | child table | Document type + prefix + format + current value |

## Child tables

- `ZG Number Series Item` → parent `ZG Number Series Settings.series_items`
- `ZG Sales Invoice Naming Rule` → parent `ZG Sales Invoice Naming Settings.rules` (one row per user + company)
- `ZG Mode of Payment Account` → parent `Mode of Payment.custom_zg_accounts` (allowed ledger accounts per payment method + company; see `multi_payment.md`)
- `ZG Payment Allocation` → parent `Payment Entry.custom_payment_details` (payment split across methods / accounts; see `multi_payment.md`)

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
| ZatGo Core | ZG Application Registry | List | 15 |
| ZatGo Core | ZG Application Settings | Single | 6 |
| ZatGo Core | ZG Audit Log | List | 12 |
| ZatGo Core | ZG Branch Settings | List | 16 |
| ZatGo Core | ZG Client Application | Child table | 12 |
| ZatGo Core | ZG Company Settings | List | 28 |
| ZatGo Core | ZG Config History | List | 8 |
| ZatGo Core | ZG Config Profile | List | 5 |
| ZatGo Core | ZG Delivery Boy | List | 12 |
| ZatGo Core | ZG Delivery Stop | List | 31 |
| ZatGo Core | ZG Device Token | List | 5 |
| ZatGo Core | ZG Enabled Industry | Child table | 5 |
| ZatGo Core | ZG Feature Flag | List | 9 |
| ZatGo Core | ZG Gym Attendance | List | 4 |
| ZatGo Core | ZG Gym Membership | List | 11 |
| ZatGo Core | ZG Gym Plan | List | 5 |
| ZatGo Core | ZG Integration Settings | Single | 31 |
| ZatGo Core | ZG KDS Ticket | List | 11 |
| ZatGo Core | ZG Metal Rate | List | 4 |
| ZatGo Core | ZG Mode of Payment Account | Child table | 5 |
| ZatGo Core | ZG Notification Settings | Single | 12 |
| ZatGo Core | ZG Number Series Item | Child table | 6 |
| ZatGo Core | ZG Number Series Settings | Single | 1 |
| ZatGo Core | ZG Order | List | 24 |
| ZatGo Core | ZG Order Item | Child table | 8 |
| ZatGo Core | ZG Payment Allocation | Child table | 7 |
| ZatGo Core | ZG Payment Settings | Single | 13 |
| ZatGo Core | ZG Printer Settings | Single | 14 |
| ZatGo Core | ZG Registered Application | List | 13 |
| ZatGo Core | ZG Sales Invoice Naming Rule | Child table | 5 |
| ZatGo Core | ZG Sales Invoice Naming Settings | Single | 2 |
| ZatGo Core | ZG Security Settings | Single | 15 |
| ZatGo Core | ZG Service Ticket | List | 8 |
| ZatGo Core | ZG Setting Section | List | 13 |
| ZatGo Core | ZG Storage Settings | Single | 19 |
| ZatGo Core | ZG Sync Settings | Single | 7 |
| ZatGo Core | ZG System Settings | Single | 30 |
| ZatGo Core | ZG Table | List | 8 |
| ZatGo Core | ZG Trip | List | 18 |
| ZatGo Core | ZG User Preferences | List | 9 |
| ZatGo Core | ZG Van Sale Profile | List | 18 |
| ZatGo Core | ZG Van Sale Profile Access | Child table | 2 |
| ZatGo Core | ZG Vehicle | List | 5 |
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
