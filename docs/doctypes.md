# DocTypes — ZatGo Core

Module: **ZatGo Core**

## Singles (global)

| DocType | Purpose |
|---------|---------|
| ZG System Settings | Language, timezone, currency, branding, defaults, fiscal year, theme |
| ZG Integration Settings | WhatsApp, SMS, Email, Firebase, Maps, AI providers, OAuth/JWT, webhooks |
| ZG Printer Settings | Receipt / kitchen / barcode / label / A4, margins, auto/silent print |
| ZG Payment Settings | Cash/card/bank/wallet/gift card, split, tips, service charge, round-off |
| ZG Notification Settings | Desktop, push, email, SMS, WhatsApp, Telegram, Slack, in-app |
| ZG Storage Settings | Local/S3/R2/Drive/Dropbox/Azure + backup retention |
| ZG Security Settings | Password policy, OTP/2FA, session, IP/devices, audit, API keys |
| ZG Sync Settings | Offline mode, interval, retry, conflict strategy, Redis queue |
| ZG Number Series Settings | Child table of prefixes/sequences for all document types |

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

## Why not literal "System Settings"?

Frappe already ships `System Settings`. Using `ZG *` keeps the ecosystem safe on
shared sites and makes ownership obvious in Desk search.
