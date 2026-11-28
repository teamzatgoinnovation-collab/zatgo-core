# ZatGo settings

*Phase 7, 2026-11-28.*

## Where a setting lives
**ERPNext's own settings first.** A ZatGo setting exists only where ZatGo adds behaviour ERPNext does not have, so there is one source of truth for each value.

The **ZatGo Settings** workspace (Apps screen) is the landing page: ten sections, each linking the native setting first.

| Section | ERPNext / Frappe | ZatGo |
|---|---|---|
| General | System Settings (language, date and number format, time zone, password policy, 2FA, sessions), Global Defaults (default company, currency), Company, Currency | ZatGo System Settings (app switches, industries, auto-fill options) |
| Modules | — | Module Settings, ZatGo Apps hub, Licence |
| Sales | Selling Settings, Price List | Sales Invoice Naming Settings (series and print format per user), VanSaleX Settings, ZatGo POS Settings |
| Purchase | Buying Settings, Supplier Group | — |
| Inventory | Stock Settings, Warehouse, UOM, Item Group | — (source-warehouse auto-fill is in ZatGo System Settings) |
| Accounting | Accounts Settings, Mode of Payment (+ allowed accounts), Fiscal Year, Currency Exchange Settings | Company Settings (default tax template, accounts, warehouse per company) |
| Print | Print Settings, Print Format, Letter Head | print format per user (in Sales Invoice Naming Settings) |
| Tax and Compliance | Sales / Purchase Taxes and Charges Template, Item Tax Template, Tax Category | ZATCA Phase 1 QR is automatic (`services/zatca_qr.py`); the seller VAT number is the Company's |
| Users and Access | User, Role, Role Permissions Manager, User Permission, Role Profile | Van Sale Profile (per-user van rules) |
| Advanced | Error Log, Scheduled Job Log | Integration Settings, ZatGo Notification Settings, Application Settings, Duplicate Prevention Settings, Audit Log |

Who sees the page: System Manager, ZatGo Application Admin and ZatGo Company Admin. Inside it, each link shows only to users who may open it.

## Settings that do nothing (found in Phase 7)
No server code and no ZatGo client app reads these. They are **not deleted**, and their stored values stay. They are removed from the navigation, and each form now opens with a notice saying where the real setting is:

| DocType | Real setting |
|---|---|
| ZatGo Security Settings | Frappe System Settings (password policy, 2FA, session expiry, login attempts) |
| Payment Settings | ZatGo POS Settings; Mode of Payment accounts |
| Printer Settings | Print Settings, Print Format, ZatGo POS Settings |
| Sync Settings | VanSaleX Settings, ZatGo POS Settings → Offline |
| Storage Settings | the bench (site_config, Frappe backups) |

In **ZatGo System Settings** the copies of Frappe settings that nothing reads are hidden (data kept): time zone, date format, rounding method and precision, multi-company and branch mode. Parts of Integration Settings (Firebase JSON, webhooks, GraphQL, OAuth flags) and Notification Settings are also unread. They stay visible for now and are listed in `TECHNICAL_AUDIT.md`. **Before** wiring any of them to behaviour, decide whether ERPNext already has the setting.

## Rules enforced
- **Who switches**: apps, industries and modules are switched by a System Manager only, in the controllers (`app_authority`, `module_settings`).
- **Company and branch settings**: the role matrix (`permissions/guards.py`) admits the category. The read checks the document as well, so a Company Admin with a Company User Permission reads only their companies' settings (`SettingsService.get_company_settings`). Writes go through `doc.save()`, which applies the same permission.
- **A save sets only editable fields**: `repositories/settings_repository.writable_values`. Unknown keys, standard fields (`name`, `owner`, `docstatus`, ...) and read-only fields are dropped and logged.
- **Defaults are stored**: a ZatGo checkbox that is on by default gets a patch that stores the 1, or the form would open unticked (v0_4_5, v0_4_6, v0_4_7, v0_4_9).
- **Settings never rewrite documents**: a change applies to what is created next. One known exception: saving Company Settings with "Enable Negative Stock" also sets the global Stock Settings value for all companies (`settings_service.save_settings`). It is kept for compatibility and listed for Phase 9.
