# ZatGo Core duplication audit — 2026-10-31

Method: 14 read-only audit passes (every DocType of zatgo-core, the Custom Fields / Property Setters it creates on ERPNext and
Frappe documents, the same concept stored in several settings places, and duplicate code) over `zatgo_core` on `main` (`c48b9d0`, with the retail POS and MyBis backend commits), compared
with the ERPNext and Frappe source in the dev bench; then every medium or high finding was re-checked by an independent
verifier whose job was to refute it (two verifiers with different lenses for the high ones). Static audit: nothing was run on a
site. Four of the claims were re-checked by hand against the code afterwards and hold: the ZATCA QR and the ZG print formats read
`ZG Company Settings.tax_id` before `Company.tax_id` (`services/zatca_qr.py:53-59`, `setup/ensure_print_formats.py:56`), the
negative-stock flag is pushed to Stock Settings only on an API save (`services/settings_service.py:111`), `ZG Security Settings`
is only validated (`validation/security.py`) and never applied, and `ZG Number Series Settings` has only a seed and a validator
(`setup/seed_defaults.py`, `validation/number_series.py`).

Read-only audit of zatgo-core (Frappe v16) for duplicate DocTypes, fields, data and logic, against ERPNext/Frappe and within the app itself.

## 1. Headline

| Measure | Count |
|---|---|
| DocTypes audited | 72 |
| Verdict: unique | 26 |
| Verdict: extends_standard | 15 |
| Verdict: overlaps_standard | 19 |
| Verdict: internal_duplicate | 8 |
| Verdict: duplicates_standard | 4 |
| Findings confirmed | 39 (26 medium, 13 low, 0 high) |
| Findings contested | 1 (pos-1) |
| Findings refuted | 11 |
| Additional low-severity notes (not verified as findings) | 36 |

The three most important conclusions:

1. **Most duplication is dead settings storage, not live double bookkeeping.** ZG System Settings, ZG Company Settings, ZG Security Settings, ZG Payment Settings, ZG Number Series Settings and ZG POS Settings repeat fields that Company, Global Defaults, System Settings, Stock Settings or Document Naming Settings already own. Almost nothing reads the ZG copies. An admin who edits them sees no effect, and the security and payment screens give a false sense of control. No verifier rated any finding high. None found a parallel GL or stock-posting engine.
2. **A few copies are read and can silently disagree with the standard value.**
   - The ZATCA QR and ZG print formats take the VAT number from ZG Company Settings.tax_id first, and only fall back to Company.tax_id.
   - `enable_negative_stock` overwrites the site-wide Stock Settings flag, and only when saved through the API.
   - ZG Mode of Payment Account.is_default can override the native default account.
   - Admin versus field-user is defined twice, by role and by profile `user_type`.
   - Default warehouse and default company are resolved by different chains in VanSaleX and POS.
3. **The financial write path repeats the same glue in six places.** Insert-idempotent, submit, commit and rollback are copied across the VanSaleX, Resto, Retail, erpnext_writes and purchase services. The copies have drifted: only Retail retries the MariaDB 1020 naming race, and only some log the real error. Posting itself still goes through ERPNext documents.

## 2. Confirmed duplicates, ordered by severity

No confirmed finding is high. Medium findings come first, then low. Within a severity level, rows are grouped by theme.

| ID | Severity | What is duplicated | Standard counterpart | Source of truth today | Recommendation | Migration risk |
|---|---|---|---|---|---|---|
| code-duplication-1 | medium | Insert, submit, commit and rollback pipeline for invoices, hand-copied in 6 places and drifted | services/idempotency.py (insert step only); ERPNext `submit()` | services/idempotency.py | Add one `post_idempotent` helper (retry, submit, commit, rollback, log, reason) and call it from all engines. Keep per-engine replay checks outside it. | Medium. Touches every invoice-posting path. Replay and rollback semantics must be unchanged. Needs a concurrent-duplicate test. No schema change. |
| code-duplication-3 | medium | Resto and Retail POS build the Sales Invoice and Payment Entry as two copies. Retail added mode-of-payment account and bank reference, and Resto did not get them. | Retail `create_sale` vs Resto `pay` | retail_pos_service (more complete) | Extract one shared POS checkout service. Do not merge the order or table DocTypes. | Medium. Resto Card/Wallet payments may debit a different ledger. Test each mode of payment. |
| vansalex-2 | medium | "Admin" and "field user" defined by role and by `ZG Van Sale Profile.user_type`. Three readers use different sources. | Role, Has Role (VanSale Admin / VanSale User) | Frappe roles for authorization | Derive `user_type` from the role. Make the profile pure van config. | Medium to high. Profiles marked Admin without the role would become field users and hit stock and money limits. Grant roles by patch first. The Flutter app reads `user_type`. |
| payments-naming-1 | medium | ZG Mode of Payment Account `is_default` vs native `default_account` | Mode of Payment Account | Native default for the default, ZG rows for extra allowed accounts | Keep the ZG table. Write the ZG default through to native, or drop `is_default`. Warn when native default is not in the allowed list. | Medium. Rows whose `is_default` differs from native would change the API default account. Check per site. No GL change. |
| platform-a-2 / cross-settings-4 | medium | ZG Company Settings.tax_id, read before Company.tax_id by the ZATCA QR and ZG print formats | Company.tax_id | Company.tax_id (intended). The ZG value wins when set. | Remove the ZG field and read Company only. If an override is wanted, validate equality. | Medium. Run a per-site report of differing values first. Print formats are stored in the DB and need a refresh. Compliance-sensitive. |
| platform-a-4 / cross-settings-5 | medium | `enable_negative_stock` (per company) pushed to site-wide Stock Settings.allow_negative_stock, only on API save. `stock_valuation_method` is a dead copy. | Stock Settings | Stock Settings | Delete both ZG fields and the sync block. Have desktop-accounting edit Stock Settings directly. | Medium. Alters inventory behaviour. Compare values per site before removal. desktop-accounting settings page needs a UI change. |
| code-duplication-7 | medium | Four company resolvers and three warehouse chains. POS guesses the first Warehouse, VanSaleX does not. | erpnext `get_default_company`; Stock Settings.default_warehouse | ZG Company Settings.default_warehouse, then Stock Settings | One strict company resolver and one `resolve_warehouse(company)`. | Low to medium. Sites relying on the POS first-warehouse fallback would fail with a clear error. |
| platform-a-6 / cross-settings-2 | medium | Default warehouse stored in 4 to 6 places (System, Company, POS Settings, Branch, Profile). Resolution order differs by entry point. | Stock Settings.default_warehouse | ZG Company Settings override, then Stock Settings | Delete the System Settings copy. Wire or remove the POS Settings copy. Use one helper. | Low for the field delete. Test van sale and POS warehouse selection. |
| cross-settings-1 | medium | Default company in ZG System Settings, Tracker Settings and MyBis Settings, beside Global Defaults and the user default | Global Defaults.default_company | Global Defaults and user default | Delete ZG System Settings.default_company (boot reads Global Defaults). Keep Tracker and MyBis only as documented overrides. | Low to medium. Check Desk JS reading `boot.zatgo_core.system.default_company`. Keep VanSaleX strict. |
| platform-a-1 | medium | ZG System Settings copies: timezone, country, currency, date_format, fiscal_year, rounding_*, default_warehouse, default_cost_center, default_company | System Settings, Global Defaults, Stock Settings | Frappe and ERPNext copies | Delete the unread fields. Link to the standard screens instead. | Low. Check mobile and desktop clients using `get_system_settings`. Response shape changes. Drop columns by patch and verify with `information_schema`. |
| cross-settings-3 | medium | Currency in ZG Company Settings (copied once at creation, never synced) and ZG System Settings | Company.default_currency, Global Defaults.default_currency | Company and Global Defaults | Delete both ZG fields and the copy in `events/company.py`. | Low. Check settings API and SDK types. |
| platform-a-5 / cross-settings-10 | medium | ZG Company Settings fields that repeat Company (accounts, cost center, logo, email, letter head, terms, valuation method) | Company | Company | Delete the unread copies. Keep tax template, POS flags, colours. | Medium. Report differing values first and copy into Company where empty. Check `get_company_settings` clients. |
| cross-settings-9 | medium | Cash and bank defaults across Profile, VanSaleX Settings, ZG Company Settings and the Payment Entry chain. Cash never reads Company.default_cash_account. | Company.default_cash_account, Mode of Payment Account | Company and Mode of Payment, with documented VanSaleX overrides | Remove ZG Company Settings.default_cash_account. Delete ZG Payment Settings.round_off_account. | Medium. Sites that filled only the ZG field lose the cash account unless copied first. |
| vansalex-1 | medium | Default cash and bank account in VanSaleX Settings and ZG Company Settings. The cash chain ignores Company, the bank chain reads it. | Company defaults, Mode of Payment Account | Company and Mode of Payment, plus the per-driver profile override | Remove the company-level copies. At minimum add Company to the cash chain. | Medium. Patch to copy differing values. Kasibasia may hold a VanSaleX-only value. |
| platform-b-1 | medium | ZG Security Settings (password, 2FA, session, lockout) is validated but never enforced | System Settings | System Settings | Drop the duplicated fields or write through to System Settings. Wire or delete the extras. | Low data risk. Touches the doctype, validator, constants, cache, API mapping, manifest and a test. Needs a column-drop patch. |
| platform-b-2 | medium | ZG Number Series Settings / Item, a parallel numbering registry that no code reads | Document Naming Settings, Series | Frappe Series, plus ZG Sales Invoice Naming Settings | Delete both DocTypes, the seed, validation and test. | Low. Seeded rows are only defaults. No document name depends on them. Many files touched. |
| platform-b-5 | medium | ZG Payment Settings round-off account and method toggles; no reader | Company.round_off_account, Mode of Payment | Mode of Payment and Company | Remove `round_off_*` and the toggles. Keep tips, service charge and split only if wired. | Low. Repoint workspace shortcuts and manifests. |
| registry-audit-3 | medium | Three change trails for one settings edit: Version, ZG Audit Log, ZG Config History. Reset writes an extra row. | Version, Activity Log | ZG Audit Log for security, Version for content | Keep Audit Log. Drop `track_changes` or the mixin. Remove the extra Reset row. | Medium. Desk timeline loses history going forward. Do not delete Audit Log rows. |
| pos-2 | medium | ZG KDS Ticket.status vs ZG Order Item.status. Nothing writes back, so orders report stale state. | ZG Order Item (internal) | ZG KDS Ticket should own preparation status | Write status back, or derive it from tickets. Link the ticket to the order. | Medium. Touches KDS and POS clients. Existing tickets have no link, so back-fill needs a match on order number plus item name. |
| delivery-fleet-1 | medium | ZG Vehicle still live beside ERPNext Vehicle. Both are seeded and read. Out of active scope. | Vehicle | ERPNext Vehicle | Retire ZG Vehicle and repoint the fleet API. Do this only when asked. | Medium. API shape changes. Rows created after the patch must be re-copied. |
| chat-core-1 | medium | AI provider API keys in Chat AI Settings and ZG Integration Settings; only the first is read | ZG Integration Settings (internal) | Chat AI Settings | Fall back to the integration key, or remove the unused AI fields. | Low to medium. Password fields on two Singles. Copy saved keys before removal. |
| custom-fields-6 | medium | `vansale_amount_in_words_print` is a second copy of `in_words`. It uses `grand_total`, not `rounded_total`, so it can differ. | Sales Invoice.in_words | ERPNext `in_words` | Bind print formats to `in_words`. Delete the field. Verify print_designer on a site first. | Low. Repoint print formats. |
| code-duplication-4 | low | Return-quantity validation re-implemented four times | erpnext `sales_and_purchase_return.py` | ERPNext | Parameterise the twins by doctype. Drop redundant pre-checks. Keep `_apply_return_qtys`. | Low to medium. Return, credit-note and debit-note flows. Test partial, repeated and multi-line returns. |
| code-duplication-5 | low | `create_receive_payment` and `create_pay_payment` are identical bodies | `get_payment_entry` | One parameterised service function | Collapse into one function keyed by doctype. Keep thin wrappers. | Low. Keep public endpoint names. |
| code-duplication-8 | low | Three definitions of a valid Bank/Cash account and two resolvers | `get_bank_cash_account` | services/payment_entry_accounts.py | Make `payment_entry_accounts` the single definition. | Low to medium. May change which accounts VanSaleX accepts. |
| chat-ops-1 | low | Six-field health block and check loop copied across 3 AI connector DocTypes | n/a (internal) | Each connector's own row | Share one helper. Align the default status. Do not merge the DocTypes. | Low if code only. |
| platform-b-3 | low | Number Series registry claims Sales Invoice numbering | ZG Sales Invoice Naming Settings | ZG Sales Invoice Naming Settings | Falls away when platform-b-2 is done. | None beyond platform-b-2. |
| platform-b-6 | low | ZG Integration Settings SMS, Slack, webhook and OAuth entries; no consumer | SMS Settings, Slack Webhook URL, Webhook, OAuth Settings | Frappe integrations | Remove `sms_*` and `slack_*`. Keep keys with a real consumer. Claim is narrower than first written. | Low to medium. Password fields to purge. |
| platform-b-7 | low | Channel toggles and Firebase credentials repeated in Notification and Integration settings | ZG Integration Settings (internal) | Credentials in Integration Settings, routing in Notification Settings | Keep credentials in one place. `devices.py` must read it. | Low. One-time copy of `fcm_server_key`. |
| registry-audit-1 | low | ZG Application Registry, an orphan legacy list with no writer | ZG Registered Application, Installed Application | app_catalog plus ZG Registered Application | Delete the DocType and its wiring. | Low. Confirm `tabZG Application Registry` is empty first. A delete patch is needed. |
| custom-fields-2 | low | `zatgo_client_id` field definition copied across patches. ZG Trip carries it as a Custom Field. | n/a (internal) | The idempotency design | One constant to build all Custom Fields. Declare the field in `zg_trip.json`. | Low. Field template must be byte-identical. Verify the unique index afterwards. |
| custom-fields-5 | low | Customer balance by hand-written SQL vs `get_balance_on`; stored snapshots | `erpnext.accounts.utils.get_balance_on` | ERPNext helper | Call `get_balance_on` and delete `_customer_balance`. | Low to medium. Printed balances on new invoices may differ slightly. |
| custom-fields-7 | low | Company `vansale_bank_*` free-text fields | Bank Account, Company.default_bank_account | Bank Account | Read Bank Account in the print template. | Medium. Existing typed values must become Bank Account docs first. |
| cross-settings-7 | low | Timezone, country, date format, rounding and fiscal year in ZG System Settings. Subset of platform-a-1. | System Settings, Global Defaults | Frappe | Delete the fields and link to the standard screens. | Low. |
| cross-settings-8 | low | Default price list and customer in ZG Company Settings and ZG POS Settings; unread | Selling Settings, POS Profile | Selling Settings (site), POS Profile (terminal) | Remove the Company copy. Drop or wire the POS copies. | Low. No financial data. |


### Notes on the highest-impact items

No finding is rated high. These are the ones to read first because they touch money, tax or authorization.

- **VAT number (platform-a-2 / cross-settings-4).** The seller VAT in the ZATCA QR comes from the ZG field when set. ERPNext reports and stock print formats use Company.tax_id. The override is documented as intentional (`docs/settings_scope.md`) but is not validated against Company. The ZG field is empty by default, so harm needs a differing value. Treat as compliance-sensitive and report before changing.
- **Negative stock (platform-a-4 / cross-settings-5).** One company's API save flips stock behaviour for every company on the site. A Desk save does not sync. This is a settings facade, not a parallel posting engine.
- **Admin versus field user (vansalex-2).** The profile `user_type` can lift stock and money limits on its own. The purchase gate checks roles only. This is a divergence on an authorization boundary. A fix must grant roles before removing `user_type`.
- **Invoice posting glue (code-duplication-1).** Error handling and naming-race retry differ by engine. VanSaleX drops the failure reason and has no 1020 retry. Posting still goes through ERPNext, so the risk is diagnostics and robustness.
- **Payment defaults (payments-naming-1, vansalex-1, cross-settings-9).** Desk Payment Entry reads only the native default account. API paths read the merged result. An admin can set two different defaults with no warning.

## 3. Contested - needs a decision

### pos-1: ZG POS Settings default_warehouse, default_price_list, default_customer, default_payment_mode, max_discount_percent, allow_discounts

Original severity: high.

- **Counterpart:** POS Profile, ZG Company Settings.default_warehouse and default_price_list, VanSaleX Settings.max_discount_percent.
- **Claim:** The POS app is shown ZG POS Settings values, but invoices post using the ZG Company Settings warehouse or an arbitrary company warehouse, with a hard-coded "Walk-in Customer". The discount cap is not enforced server-side.
- **Verifier 1 (confirmed, keeps high):** Posting never reads ZG POS Settings. `_resolve_pos_warehouse` uses Company Settings and then the first warehouse. `_apply_discount` checks only 100% or the subtotal. An admin could set a warehouse in POS Settings and see stock leave a different one. Caveats: the POS Profile and VanSaleX counterparts are weaker, and the retail path was not checked.
- **Verifier 2 (not confirmed):** The overlap is real but not as serious as claimed. The repo docs describe it as a known unwired state. `docs/settings_scope.md:67` says only `pos_type` has an effect, and no client calls `pos_settings.get`. So the cashier does not see one value while stock leaves another today. It is dead or pending configuration, plus a latent risk if the client is wired up without unifying sources. The missing server-side discount cap is a separate gap.
- **Decision needed:** Either wire ZG POS Settings into posting (with a documented chain: POS Settings, then POS Profile or Company Settings, then Selling Settings) and enforce `max_discount_percent` server-side. Or delete `default_warehouse`, `default_price_list` and `default_customer` from ZG POS Settings. Keep `pos_type`, receipt text and `print_copies`. The server-side discount cap needs its own decision either way.

## 4. Checked and found justified

Do not re-report these.

**Refuted findings**

| ID | Item | Why it is justified |
|---|---|---|
| platform-b-4 | ZG Storage Settings vs System Settings.backup_limit and Dropbox/S3 | Unused placeholders. `backup_retention_days` is an age in days and `backup_limit` is a count. Nothing reads the fields, so nothing diverges. The secret is a Password field. Dead config, low severity. |
| registry-audit-2 | App identity in catalog, ZG Registered Application, ZG Client Application | The registry is a regenerated projection of the catalog with `enabled` catalog-authoritative. Client rows describe which front-end product may connect, a different object. Only labels are duplicated. |
| delivery-fleet-2 | ZG Delivery Boy vs Driver | Nothing reads Driver or Delivery Trip. Different status model, with GPS, points and a User with the Delivery role. At most a missing optional Link. Out of scope. |
| delivery-fleet-3 | ZG Delivery Stop vs Delivery Stop | The ZG stop is a courier job with status flow, POD and COD, which the standard stop lacks. Loose Data references, not a mirror. Out of scope. |
| industries-1 | Gym Membership and Plan vs Subscription | A fixed-length period with manual idempotent billing and renewal by a new record. Subscription is an automated recurring-invoice engine. Posting goes through Sales Invoice. |
| chat-ops-2 | AI Plugin Registry vs ZG Registered Application | Different objects: Chat AI plugins on an allow-list vs desk application switches. At most a low-severity cleanup. |
| tracker-space-1 | Tracker Settings.default_company vs Global Defaults | A narrower Tracker fallback, reached only for users without an Employee company. A design nit. |
| custom-fields-3 | Invoice `custom_cash_account` / `custom_bank_account` / `custom_payment_type` vs native fields | The code skips invoices with zero outstanding or an existing Payment Entry, so there is no double payment. A deliberate design. |
| cross-settings-6 | Brand, logo, theme, language across stores | Desk brand logo and document logo are different things. Legacy hidden fields are a deliberate rollback fallback. Only `ZG Company Settings.logo` and `ZG Printer Settings.logo` are dead, which is low. |
| code-duplication-2 | Sales tax template application vs `set_taxes` | It calls ERPNext's `get_taxes_and_charges` and adds a per-company template and forced inclusive pricing, which `set_taxes` cannot express. No tax maths is re-implemented. |
| code-duplication-6 | Oldest-first collection allocation vs Payment Entry allocation | It uses `get_payment_entry` and Payment Entry's own `validate()`. A deliberate FIFO that excludes credit notes, covered by tests. |

**Low-severity notes (36, not verified as findings)**

- Hidden legacy brand fields on ZG System Settings (platform-a-3), kept as a pre-migrate fallback.
- ZG User Preferences theme and language (platform-a-7), unapplied copies of User fields.
- ZG Branch Settings free-text links (platform-a-8). This extends Branch, so the overlap is small.
- ZG Printer Settings logo (platform-b-8), unread.
- ZG Config History vs Audit Log (registry-audit-4). It adds section context and action verbs, so it is not purely redundant.
- ZG Enabled Industry mirror (registry-audit-5), documented and low risk.
- ZG Config Profile `is_active` and `environment` (registry-audit-6), never read.
- ZG Payment Allocation row shape (payment-naming-2-placeholder), a managed overlap.
- Return-series heuristic vs explicit rule (payments-naming-3). The heuristic is a legitimate fallback.
- VanSaleX access catalog in three places (vansalex-3), documented maintenance duplication.
- Van warehouse binding vs POS Profile and User Permission (vansalex-4).
- ZG Order delivery fields, customer and table name copies, and unused `default_pos_profile` (pos-3, pos-4, pos-5).
- ZG Service Ticket (delivery-fleet-4), minimal and out of scope.
- Gym price snapshots, Metal Rate vs Item Price, and denormalised member names (industries-2, industries-3, industries-4).
- AI Chat Memory and Summary pair, and the AI Attachment URL copy (chat-core-2, chat-core-3).
- AI REST Tool vs Webhook, the two Provider Health Log writers, scheduler arithmetic, and connector credentials in two stores (chat-ops-3 to chat-ops-6).
- MOCK_PLANS constants and the repeated "Execution" literal (tracker-space-2, tracker-space-3).
- Custom Field inventory and the smaller custom-field overlaps: bank reference, sibling-app print fields, map URL fields, own-DocType Custom Fields (custom-fields-1, 4, 8, 9, 10).
- Printer and copies settings in four places (cross-settings-11).
- Code-level repeats: ZATCA-QR and trip-link blocks, API helpers in three packages, the single-Check reader, and Retail vs Resto API modules (code-duplication-9 to code-duplication-12).

## 5. Verdict for every DocType

| DocType | Group | Verdict | Counterparts | Note |
|---|---|---|---|---|
| ZG System Settings | platform-a | overlaps_standard | System Settings, Global Defaults, Stock Settings, Fiscal Year | Most of it is unique (app/industry switches, autofill flags, IFRS, stock_summary_live_only). But timezone, country, currency, date_format, fiscal_year, rounding_method/precision, default_company, default_warehouse and default_cost_center (zg_system_settings.json:104-161) repeat Frappe System Settings / Global Defaults / Stock Settings. Of these, only default_company is read, and only for the boot payload (events/boot.py:119). The hidden brand_name/company_logo/theme/language (json:68) are leftovers from the v0_4_10 move, kept only as a pre-migrate fallback in services/ui_settings.py:25. |
| ZG Company Settings | platform-a | overlaps_standard | Company, Stock Settings, Selling Settings, Buying Settings | One row per Company, auto-created by events/company.py. It links to Company, so it is not a copy of the Company row. Several fields do copy Company: tax_id, default_currency, logo, company_email, the default receivable/payable/cash accounts, default cost center, sales/purchase terms and valuation method. The extras are real: tax template, POS profile, branding colors. Only tax_id, default_warehouse, default_cash_account and default_tax_template have a reader. The warehouse and cash-account readers fall back to Stock Settings or the Company. |
| ZG Branch Settings | platform-a | extends_standard | Branch, POS Profile, Warehouse | ERPNext Branch has only a name field. This DocType adds per-branch operational settings (printers, shifts, delivery zone, kitchen). The link back is a plain Data field, erp_branch, not a Link, and branch_name is stored separately. The pos_profile Data field overlaps POS Profile.warehouse, but nothing reads it. Mostly unique. |
| ZG User Preferences | platform-a | overlaps_standard | User | UI preferences per user (sidebar, landing page, shortcuts, favorite apps, recents) are unique. The theme and language fields (json:36,44) repeat User.desk_theme and User.language. The only reader is the generic settings API, which returns the row as-is (SettingsService.get_user_preferences). Nothing applies the stored values to Desk. |
| ZG Application Settings | platform-a | unique | - | Registry of client apps (Electron/Flutter/Web) with auth and blocking rules. No standard equivalent exists. The older ZG Application Registry list DocType is the deprecated duplicate. It is outside this group and already marked legacy at constants/settings.py:11. |
| ZG Theme Settings | platform-a | extends_standard | System Settings, Website Settings | This is the current owner of brand_name, company_logo and theme, moved out of ZG System Settings in v0_4_10. It is read through services/ui_settings.py. It sits beside, rather than duplicates, Frappe's app name and logo. The leftover hidden copies in ZG System Settings are the problem (finding platform-a-3). |
| ZG Language Settings | platform-a | extends_standard | System Settings | Holds a single field, the default language for the language switcher, read through ui_settings. Frappe System Settings.language is the site language, a different setting with the same name. A hidden copy still sits in ZG System Settings. |
| ZG MyBis Settings | platform-a | unique | Global Defaults | Per-site limits for the MyBis app (default period, KPI hiding, export switches). Its default_company is read first and falls back to Global Defaults.default_company (api/v1/mybis/context.py:99-100). It links to Company and is a legitimate override. |
| ZG Security Settings | platform-b | duplicates_standard | System Settings | Password length/strength, 2FA, session timeout, login-attempt limit and lockout are all native System Settings (minimum_password_score, enable_password_policy, enable_two_factor_auth, session_expiry, allow_consecutive_login_attempts, allow_login_after_fail). Only validate() enforces bounds; no code outside the doctype reads min_password_length, session_timeout_minutes, login_limit, etc., so the policy is never applied. |
| ZG Number Series Settings | platform-b | duplicates_standard | Document Naming Settings, Naming Series | Parallel registry of prefix/format/current_value per document type. Seeded and validated but no naming hook, autoname or service reads it (grep of series_items/current_value finds only seed and validation), so it is an unused second numbering source next to Document Naming Settings and the live ZG Sales Invoice Naming Settings. |
| ZG Number Series Item | platform-b | duplicates_standard | Document Naming Settings, Series | Child row (document_type, prefix, current_value) mirrors Document Naming Settings 'Update Series' fields prefix/current_value; not consumed by any code. Also internally overlaps ZG Sales Invoice Naming Rule. |
| ZG Storage Settings | platform-b | overlaps_standard | System Settings, Dropbox Settings, S3 Backup Settings | Backup retention overlaps System Settings.backup_limit and the provider credentials (S3, Dropbox) overlap Frappe's backup integrations. Nothing in the app reads this doctype except settings cache invalidation and the config center listing, so the credentials are stored but unused. |
| ZG Integration Settings | platform-b | overlaps_standard | Email Account, SMS Settings, Slack Webhook URL, Webhook, Social Login Key, OAuth Settings | Aggregates SMS, email, Slack, webhooks, OAuth and AI keys. default_email_account links to Email Account rather than copying it (extension), but sms_*, slack_webhook_url, webhooks_enabled and oauth_enabled repeat SMS Settings, Slack Webhook URL, Webhook and OAuth. Read only through the generic settings API and key-presence validation; no service consumes the keys. |
| ZG Notification Settings | platform-b | overlaps_standard | Notification Settings, Push Notification Settings | Channel toggles and quiet hours; the only real reader is api/v1/devices.py (push_enabled, fcm_server_key). The other toggles (desktop, email, sms, telegram, slack, quiet hours) are unread. Frappe's per-user Notification Settings and Push Notification Settings cover the same ground, but the FCM device-token push has no Frappe equivalent, so this is a partial, justified extension. |
| ZG Payment Settings | platform-b | overlaps_standard | Mode of Payment, Company, POS Profile | cash/card/bank/wallet toggles shadow Mode of Payment enabled flags and POS Profile payment methods; round_off_account is a Link to Account but repeats Company.round_off_account. No code reads any field (only config-center links and workspace shortcuts), so it is configuration with no effect. |
| ZG Printer Settings | platform-b | extends_standard | Print Settings, Network Printer Settings | Role-based printer names (receipt/kitchen/label/barcode/A4) and paper width are not modelled by Print Settings.server_printer or Network Printer Settings, so the idea is a gap-fill. Only reader is the ZG Printer Usage report and settings API. Its logo field repeats ZG Company Settings.logo and Letter Head. |
| ZG Sync Settings | platform-b | unique | - | Offline mode, sync interval, retry, conflict strategy have no Frappe/ERPNext counterpart. Not read by any server code yet (only manifest and cache invalidation), but no duplicate source of truth. |
| ZG Application Registry | registry-audit | internal_duplicate | ZG Registered Application, Installed Application, Module Def | Legacy list of installed apps (app_name, version, app_status, module_name). Nothing seeds or reads its rows; ZG Registered Application plus app_catalog replaced it. Frappe Installed Application and Module Def already carry app_name and app_version. |
| ZG Registered Application | registry-audit | extends_standard | Installed Application, Module Def, ZG Client Application | Config-center projection of app_catalog plus hand-written manifests. It stores the site's switch state, menu and roles, which no standard DocType holds. Its title, version and enabled copy catalog data, but it is a documented one-way projection. It also has track_changes=1, so Frappe Version already records its edits; registrations additionally write a ZG Config History row. |
| ZG Client Application | registry-audit | overlaps_standard | ZG Registered Application, OAuth Client | Child table of ZG Application Settings. It lists the front-end products (Electron, Flutter, Web) that may call the site. It is not an OAuth Client because it holds no secret or redirect URI. It repeats app_key, title, icon, description and enabled from the registry and catalog, and shares app_key values such as vansalex and tracker. |
| ZG Config Profile | registry-audit | unique | - | Named JSON export of all visible settings. No standard counterpart. The environment and is_active fields are not read by any service. |
| ZG Config History | registry-audit | overlaps_standard | Version, ZG Audit Log | Change log of registry and settings edits (old/new payload, by, on). It repeats what Version and ZG Audit Log record for the same save. |
| ZG Setting Section | registry-audit | unique | - | Tree of settings sections per registered app, linking to a settings DocType or a UI component. No standard equivalent. It is rebuilt from the manifests. |
| ZG Feature Flag | registry-audit | unique | - | Per company/branch flag with rollout percent. Frappe has no feature-flag DocType. It sits beside the per-app switches in ZG System Settings but answers a finer question (flag within an app), so it is not a duplicate. |
| ZG Audit Log | registry-audit | overlaps_standard | Version, Activity Log, Access Log | Field-level old/new log written by AuditableMixin. Version with track_changes=1 records the same diffs, and every audited settings DocType has track_changes=1. It adds IP, browser, reason and password redaction, so it is partly justified. Activity Log and Access Log cover other purposes (logins, exports). |
| ZG Device Token | registry-audit | unique | Push Notification Settings, OAuth Bearer Token | Per-user FCM/APNs push tokens, owner-scoped. Push Notification Settings holds only the relay credentials, and OAuth Bearer Token is an API access token, not a device token. |
| ZG Enabled Industry | registry-audit | internal_duplicate | industries/registry.py | Child table in ZG System Settings, synced from the in-code industry registry (industries/sync.py). Label and availability are copies; the key and enabled flag are the real state. Documented, a low-risk mirror. |
| ZG Mode of Payment Account | payments-naming | extends_standard | Mode of Payment Account | Child table custom_zg_accounts on Mode of Payment. Overlaps the native Mode of Payment Account (company + default_account), but extends it from one account per company to many allowed accounts per company. The overlap is the default marker, which exists on both sides. |
| ZG Payment Allocation | payments-naming | extends_standard | Sales Invoice Payment, Payment Entry | Child table custom_payment_details on Payment Entry. ERPNext Payment Entry has one bank-side account and amount and no per-method split, so this adds a capability. It does not copy a posting. Its fields mirror Sales Invoice Payment, which the Sales Invoice side uses natively instead. |
| ZG Sales Invoice Naming Settings | payments-naming | unique | Document Naming Settings | Single mapping (user, company) to naming series, plus a block-or-default policy. ERPNext Document Naming Settings and Selling Settings only list series options per doctype and have no per-user routing. Numbering stays Frappe's tabSeries counter; the settings only choose naming_series. |
| ZG Sales Invoice Naming Rule | payments-naming | unique | - | Child rows of the settings single (user, company, normal_series, return_series, enabled). No standard counterpart. The per-driver series on ZG Van Sale Profile were moved here by a patch, so there is no live internal duplicate. |
| VanSaleX Settings | vansalex | extends_standard | Company.default_cash_account, Company.default_bank_account, Mode of Payment Account.default_account, ZG Company Settings.default_cash_account | Single of app-level switches (payment type defaults, discount cap, write-off cap, module/feature table) with no ERPNext counterpart. Only default_cash_account and default_bank_account overlap standard data (Mode of Payment Account, Company.default_*). Its warehouse and tax defaults are correctly NOT copied here: they resolve from ZG Company Settings and then Stock Settings and the company's default tax template (services/vansalex_settings.py:115-124, 205-221). |
| VanSaleX Access | vansalex | unique | - | Child table holding the per-site on/off for the VanSaleX app's own modules and features (catalog in services/vansalex_access.py:49-90). These are app UI/endpoint switches, not DocType permissions, so Role/DocPerm cannot express them. Rows are seeded by setup/ensure_vansalex_access.py. |
| ZG Van Sale Profile | vansalex | extends_standard | POS Profile, POS Profile User, User Permission, Has Role | Per-driver config (van warehouse, vehicle, route title, cash/bank account, Inherit/Yes/No overrides) with no ERPNext equivalent. POS Profile is a POS-checkout template (warehouse, payments, price list), and POS Profile User only maps a user to a profile. The profile links to User, Warehouse, Account and Vehicle instead of copying them. The only real overlap is that it is a second user-to-warehouse mapping and a second 'field user' marker (see findings). |
| ZG Van Sale Profile Access | vansalex | unique | - | Child table of per-driver switch-OFFs for VanSaleX catalog keys. It can only narrow the site-wide VanSaleX Access rows, never widen them (services/vansalex_access.py:24-26, 217-224). It is not a copy of Custom DocPerm, which governs DocType permissions rather than app features. Its access_key option list is a hard-coded copy of the catalog (see vansalex-3). |
| ZG POS Settings | pos | overlaps_standard | POS Profile, POS Settings, ZG Company Settings | Single holding default warehouse, price list, walk-in customer, default mode of payment, max discount, split payment, receipt header/footer, print copies, and the pos_type switch. POS Profile has warehouse, selling_price_list, customer, payments, allow_discount_change, letter_head and print_format. ERPNext POS Settings has different fields (invoice_fields, pos_search_fields, invoice_type, post_change_gl_entries). The Resto and Retail POS flows do not use POS Profile at all. pos_type, receipt text and print_copies have no ERPNext equivalent. The warehouse, price-list, customer and payment-mode defaults duplicate POS Profile and ZG Company Settings (see pos-1). |
| ZG Table | pos | unique | - | Restaurant floor-table state (table_code, zone, seats, Free/Occupied/Billing, covers, current_order). ERPNext v16 ships no Restaurant or Restaurant Table DocType (searched the 811 standard DocTypes). Only link to standard data is company -> Company, which links rather than copies. current_order <-> ZG Order.table is a two-way pointer maintained in resto_pos_service.py (lines 283, 452-456, 564). |
| ZG Order | pos | extends_standard | Sales Order, Sales Invoice, POS Invoice | Holds restaurant state only: table, covers, channel, server, note, delivery data, an Open/Sent/Ready/Paid/Void status. It has no totals, tax, discount or payment fields. Money lives on the Sales Invoice and Payment Entry, linked through sales_invoice and payment_entry and created in pay() (resto_pos_service.py:579-700) with zatgo_client_id idempotency. It is not a Sales Order duplicate. Overlaps are denormalised customer_name, table_name and delivery_boy_name, and delivery fields copied into ZG Delivery Stop (pos-3, pos-4). |
| ZG Order Item | pos | extends_standard | Sales Order Item, Sales Invoice Item | Child table with item_code, item_name, qty, rate, station, status, extras and kds_synced. It repeats the item/qty/rate shape of Sales Invoice Item but is the pre-payment cart, and the invoice rows are built from it at pay(). It carries no amount, tax or warehouse. Its status field is never updated after creation (pos-2). |
| ZG KDS Ticket | pos | internal_duplicate | ZG Order Item | Kitchen display ticket, one per order item. ERPNext v16 has no KDS or Kitchen Order DocType. It duplicates ZG Order Item fields (item_name, qty, station, status, extras) plus denormalised order_number, table_name, server and note. The two status fields diverge (pos-2). |
| ZG Vehicle | delivery-fleet | duplicates_standard | Vehicle | Same business object as ERPNext Vehicle. Patch v0_1_0 already migrated its rows into Vehicle and repointed ZG Delivery Boy and ZG Trip, but the DocType, its API, seed data and permissions still exist and can be written to. |
| ZG Delivery Stop | delivery-fleet | overlaps_standard | Delivery Stop, Delivery Trip | A standalone per-delivery job with free-text customer, order and invoice numbers, not tied to Delivery Note or Sales Invoice. It adds driver assignment, POD and COD that the standard Delivery Stop lacks. Out of the current active scope. |
| ZG Delivery Boy | delivery-fleet | overlaps_standard | Driver, Employee | Driver profile with phone, user link, vehicle link and live GPS. ERPNext Driver already holds full_name, cell_number, user, employee and status. Out of the current active scope. |
| ZG Trip | delivery-fleet | extends_standard | Delivery Trip | Despite its name this is a VanSaleX customer visit/route-plan row, with check-in, no-sale reason and a Sales Invoice link, not a delivery run. It links to Customer, Vehicle, Warehouse and Sales Invoice rather than copying them. It does not duplicate Delivery Trip; the name is the only overlap. |
| ZG Service Ticket | delivery-fleet | overlaps_standard | Issue, Warranty Claim, Maintenance Visit | A minimal ticket (customer, address, issue, priority, status, scheduled_at) whose customer is free text. It has no controller logic and is not linked to Issue or Maintenance Visit, which already cover the same purpose. Out of the current active scope. |
| ZG Gym Plan | industries | overlaps_standard | Subscription Plan, Item | Plan (name, duration_days, price, billing Item link) overlaps Subscription Plan (plan_name, item, cost, billing_interval) in purpose. It does link to Item for billing instead of copying it (zg_gym_plan.json), but price is stored separately from the Item's Item Price. Subscription Plan only supports interval-based recurrence (day/week/month/year with count), so a fixed 'N days' plan can be approximated but not exactly. Low risk, partly justified by the gym domain. |
| ZG Gym Membership | industries | overlaps_standard | Subscription | A member's period on a plan with start/end/status and billing via Sales Invoice; ERPNext Subscription (party_type/party, start_date, end_date, status, plans, company) models the same recurring party-plan relationship. But Subscription auto-generates recurring invoices while the gym flow creates one idempotent Sales Invoice per membership and renews by creating a new record (industries/gym/service.py:14-64), so it is a deliberate domain-specific layer that links to Customer and Sales Invoice. No copy of Customer data except member_name. |
| ZG Gym Attendance | industries | unique | Attendance, Employee Checkin | Member check-in/out log. ERPNext Attendance/Employee Checkin are employee-only (HR); no standard member visit log exists in the installed ERPNext/Frappe. |
| ZG Metal Rate | industries | overlaps_standard | Item Price, Currency Exchange | Dated rate per gram by metal+purity, read by latest_rate (industries/jewellery/service.py:12-22). Item Price has valid_from/valid_upto and price_list_rate per Item+UOM and could hold it if each metal/purity had a rate Item; Currency Exchange is currency-pair only and does not fit. The jewellery price is computed (net weight x rate + wastage + making), not stored as an Item Price, so there is a single reader and no second source of truth for the same value. |
| AI Chat Session | chat-core | unique | - | Conversation container (mode, language, pin, user). No Frappe equivalent; Comment/Communication are record-bound, not threads. |
| AI Chat Message | chat-core | unique | - | LLM turn log with role, tool calls, tokens, cost, latency; Comment/Communication have none of this. |
| AI Chat Memory | chat-core | internal_duplicate | AI Conversation Summary | One row per session with entities_json and context_snapshot, used only by orchestrator.py. Overlaps AI Conversation Summary as per-session condensed state. |
| AI Conversation Summary | chat-core | internal_duplicate | AI Chat Memory, AI Chat Session | Rolling summary plus message_count. AI Chat Session.summary links to it and it links back via session. |
| AI Artifact | chat-core | unique | - | Structured outputs linked to session and message; not a Note or File. |
| AI Attachment | chat-core | extends_standard | - | Wrapper over Frappe File (attachments.py:61-68) adding extraction status, chunk_count, extracted_text. Only copied value is file_url. |
| AI Search Index | chat-core | extends_standard | - | Chunk and embedding store. Frappe global search (search/__init__.py:59-63) has no embeddings, so this is justified. |
| Chat AI Settings | chat-core | overlaps_standard | ZG Integration Settings | Single with 89 fields. Provider api_key overlaps the AI Providers section of ZG Integration Settings, which chat_ai never reads. |
| AI Integration Connector | chat-ops | internal_duplicate | AI REST Tool, AI MCP Server | Third-party service credentials (token, base URL, scopes) have no Frappe counterpart, so the DocType is needed. It repeats the same 6-field health/lifecycle block as AI REST Tool and AI MCP Server (see chat-ops-1). |
| AI MCP Server | chat-ops | internal_duplicate | AI REST Tool, AI Integration Connector | MCP servers (sse/stdio/http, discovered tools) have no ERPNext or Frappe counterpart. Only overlap is the copied lifecycle/health block shared with its two siblings. |
| AI Plugin Registry | chat-ops | internal_duplicate | ZG Registered Application | No ERPNext or Frappe counterpart, but it is a second registry of installed plugins/apps beside ZG Registered Application. Its only reader is the chat plugin-list endpoint, which falls back to the in-memory list. |
| AI Provider Health Log | chat-ops | unique | - | Time series of LLM provider ping results (ok, latency, capabilities). Scheduled Job Log, Error Log and Integration Request do not hold this. Two code paths write it (see chat-ops-4). |
| AI REST Tool | chat-ops | unique | Webhook, Integration Request | Defines a model-callable outbound HTTP tool: URL template, JSON schema, role gate, Password token. Frappe Webhook is DocType-event triggered with no schema or role gate; Integration Request is a log. Not a duplicate. |
| AI Scheduled Task | chat-ops | unique | Scheduled Job Type, Auto Repeat | Per-user scheduled LLM prompt, run as that user with unattended read-only tools. Scheduled Job Type runs a fixed Python method system-wide and Auto Repeat clones a reference document; neither runs a prompt as a user. The tick is a plain scheduler hook. Its schedule maths overlaps Frappe slightly (see chat-ops-5). |
| AI Tool Log | chat-ops | unique | Activity Log, Error Log | Per-call audit of model tool invocations (args, result, permission_ok, latency, session). Activity Log, Access Log, Error Log and Version have no such fields. It is deliberately excluded from search indexing and is owner-scoped. |
| AI Usage Daily | chat-ops | unique | - | Per user/day/model token and cost counters, and the source of truth for quota enforcement in core/quota.py. Nothing standard stores LLM tokens or cost. Increments are atomic SQL updates. |
| Tracker Activity Session | tracker-space | extends_standard | Timesheet, Timesheet Detail, Project, Task, Activity Type, Employee | Live timer state (Running/Paused/Stopped, started/paused/ended, duration_seconds) that Timesheet lacks. Links user, employee, company, project, task, activity_type and timesheet instead of copying them. On stop, services/activity.py:264-330 flushes to a draft Timesheet via insert/save (hours, project and task go in the Timesheet Detail row). duration_seconds repeats Timesheet Detail hours only until flush, so it is an in-flight copy and acceptable. |
| Tracker Settings | tracker-space | overlaps_standard | Global Defaults, Projects Settings | default_company restates Global Defaults default_company (read as a fallback chain in tracker/permissions/hierarchy.py:31-44). default_activity_type has no standard counterpart (Projects Settings holds only overlap and billing flags). |
| Space Job Log | tracker-space | unique | - | Provisioning job log for a Space Order. Links to Space Order. Nothing in ERPNext covers it. |
| Space Order | tracker-space | unique | Sales Order | A tenant-site provisioning order (slug, hostname, status, RAM and disk usage, desk_url). It is not a sales document and has no accounting impact. Its SO-.YYYY.-.##### series prefix is confusingly close to Sales Order but does not collide with ERPNext's SAL-ORD series. |
| Space Order App | tracker-space | unique | - | Child table of the apps requested for a site (package, title). No ERPNext equivalent. |
| Space Plan | tracker-space | unique | Subscription Plan, Item | Hosting plan with RAM and disk quotas plus a mock price string and a features JSON. It is not linked to Item or Subscription Plan, and nothing is billed from it (mock prices). It does not duplicate Subscription Plan, which has no quota fields. Real billing would need to link Subscription Plan or Item instead of mock_price. |
| Space Settings | tracker-space | unique | - | RAM and disk pool sizes for the hosting pool. Nothing in ERPNext covers it. site_config keys can override it (see tracker-space-2). |

## 6. Suggested order of cleanup

**Must not be touched without a separate, explicit decision:**

- Financial documents: Sales Invoice, Purchase Invoice, Payment Entry, Journal Entry, GL Entry, Stock Ledger Entry. Never edit or delete submitted documents. Any fix goes through cancellation, reversal or credit/debit notes.
- `zatgo_client_id` fields and their unique indexes. Do not change the name, type or unique flag on ERPNext doctypes.
- Anything with live data: ZG Audit Log rows (the audit trail), ZG Sales Invoice Naming Settings and Rules (live numbering), and Version rows already written.
- The out-of-scope products (delivery, fleet, service ticket, Space, Tracker) unless explicitly requested.

**Order, smallest risk first:**

1. **Documentation and dead-screen warnings, no schema change.** Correct `docs/doctypes.md`, `installation.md` and `user_manual.md`. They still describe ZG Number Series as the central registry, ZG Security Settings as the policy screen, and ZG System Settings as where the default company is set. Add the default-warehouse and default-company chains to `docs/settings_scope.md`.
2. **Code-only unification, no data change.**
   - Share the idempotent post, submit and rollback helper (code-duplication-1), with a concurrent-duplicate test.
   - Share the connector health helper (chat-ops-1).
   - Share the receive/pay Payment Entry function (code-duplication-5).
   - Share the return-quantity helper (code-duplication-4).
   - Use one payment-account validity definition (code-duplication-8).
   - Use one `zatgo_client_id` field template (custom-fields-2), after verifying the indexes with `information_schema`.
3. **Delete provably unread copies. Needs a column-drop patch and a client check, but no data migration.**
   - Unread fields in ZG System Settings (platform-a-1, cross-settings-3, cross-settings-7).
   - `ZG Company Settings.default_price_list` and the unread Company copies (platform-a-5).
   - ZG Payment Settings toggles and `round_off_account` (platform-b-5).
   - The redundant AI keys (chat-core-1), after copying any saved key.
   - ZG Number Series Settings and Item (platform-b-2, platform-b-3).
   - The legacy ZG Application Registry (registry-audit-1), after confirming the table is empty.
   - Confirm that the mobile, desktop and SDK clients do not read these keys.
4. **Make one owner for each default, which changes behaviour.**
   - Default company (cross-settings-1) and default warehouse (platform-a-6, code-duplication-7).
   - POS Settings decision (pos-1).
   - Cash and bank default chains (vansalex-1, cross-settings-9).
   - Print `in_words` (custom-fields-6).
   - Test per site, especially sites relying on the POS first-warehouse fallback.
5. **Data migration required, per-site report first.**
   - `tax_id`: report where ZG and Company differ, copy into Company where empty, report conflicts, then remove the ZG field (platform-a-2). Refresh stored print formats.
   - `enable_negative_stock`: compare each site's Stock Settings against the ZG flags before removing the sync (platform-a-4).
   - Mode of Payment defaults: compare ZG `is_default` against native `default_account` (payments-naming-1).
   - Bank details: turn typed `vansale_bank_*` values into Bank Account records (custom-fields-7).
   - Config trails: turn off `track_changes` on settings doctypes (registry-audit-3). Keep ZG Audit Log.
6. **Authorization and workflow changes. These need the most care and a Flutter release.**
   - Role versus `user_type` (vansalex-2): grant roles by patch first.
   - Shared POS checkout service (code-duplication-3).
   - KDS status write-back (pos-2), with back-fill by order number plus item name.
   - Retire ZG Vehicle (delivery-fleet-1), only if the fleet module is requested.

## 7. Not covered

`not_covered` is empty. All 72 DocTypes in scope received a verdict. The scope covers only the groups listed above. Other DocTypes in zatgo-core outside those groups were not part of this audit.