# Duplicate Prevention & Smart Record Lookup — ZatGo Core

One configurable engine that stops duplicate master records on **every** entry point (Desk, REST, Data Import, the POS / VanSaleX / accounting APIs, Flutter): a `validate` hook on the supported DocTypes, plus a live lookup in Desk and a smarter Link search. Matching is on **business identifiers**, not on the document name alone.

Switch: `enable_duplicate_prevention` in ZG System Settings → Apps (on unless switched off). Global behaviour: **ZG Duplicate Prevention Settings**. Per-DocType behaviour: **ZG Duplicate Rule**. Audit trail of overrides: **ZG Duplicate Override Log**.

## Behaviour

| Level | When | Default |
|---|---|---|
| strong | an exact *Unique Identifier* matches (VAT, CR no., barcode, item code, employee no., user ID …), or several identifiers match (e.g. mobile **and** e-mail; name **and** mobile) | **Block** |
| possible | the *Name* alone matches, or a *Shared* identifier (phone / e-mail) matches — including one that several existing records already share | **Warn** (save allowed, message shown; Desk asks once) |
| suggest | fuzzy name similarity (≥ threshold, default 85 %) | suggestion only, never blocks |

Compound identifiers (rule field `Group`): fields with the same group must **all** match, e.g. Purchase Invoice `bill_no` + `supplier`, Account `account_number` + `company`, Contact `first_name` + `last_name`.

Existing duplicates never block unrelated edits: on update the check runs only when an identifying value changed, and the document itself is excluded.

Transaction rules (`Rule Type = Transaction`) ignore cancelled documents. Seeded: Purchase Invoice (`bill_no` + `supplier`, Block), Sales Invoice (`po_no` + `customer`, Warn — several invoices may bill one customer PO).

## Normalisation (`services/duplicate/normalizers.py`)
E-mail trimmed + lower-cased. Phone: digits with the country code kept (`+966 50…`, `00966…`, `050…`, `50…` agree; other countries' `+`/`00` numbers keep their code). Tax / registration numbers: separators dropped, Arabic-Indic digits → ASCII. Names: NFKC, case-folded, Arabic diacritics/tatweel removed, alef / ya / ta-marbuta unified. Codes / barcodes: **trimmed only**. Stored values are never rewritten.

## Authorized override
Users holding one of the rule's override roles (else the Settings roles; default System Manager) can save over a *blocking* match, with a reason (configurable). Desk: the panel shows **Override (authorized)** → reason → save within 10 minutes. API: set `doc.flags.zg_duplicate_override` / `zg_duplicate_override_reason` in Python, or send `zg_duplicate_override=1` and `zg_duplicate_override_reason` as request parameters. Every override writes a ZG Duplicate Override Log row in the same transaction. A user without the role is refused whatever they send.

## Concurrency
For exact unique identifiers the check-then-insert is serialised by a MariaDB named lock per normalised identifier (`GET_LOCK`, 10 s, released at commit/rollback) and re-read with locking reads. MariaDB 11.8 (`innodb_snapshot_isolation`) answers such a read of a row committed after the transaction's snapshot with error 1020 — treated as "duplicate just created". **No new database UNIQUE constraints** are added: ERPNext's tax/mobile columns legitimately repeat in existing data; the only UNIQUE key involved remains `zatgo_client_id`.

## Live lookup and Link search
`public/js/zg_duplicate_lookup.js` (+ `public/css/zg_duplicate_lookup.css`, loaded only while the app is on): on a **new** form, typing in an identifying field (debounced 400 ms, identical requests not repeated) calls `api/v1/duplicate/lookup.check` and shows an inline panel under the field — ID, title, matched fields, configured details, **Open Existing**, **Use Existing** (fills the Link field the form was opened from, else opens the record), **Override** where permitted. No dialog per keystroke; one confirm at save only for warn-level matches.

`frappe.desk.search.search_link` is overridden (`services/duplicate/link_search.py`): the standard result runs first and is kept; records whose VAT / phone / e-mail / barcode equals the typed text are added, and identifying details are appended to descriptions (`ABC Trading — VAT: 310…`). Any error falls back to the standard result. It sits outside the gated `api/` tree so Link fields work with the app off.

## API (`zatgo_core.api.v1.duplicate.lookup`, 404 while the app is off)
`form_config(doctype)`, `check(doctype, values, exclude)`, `override(doctype, names, reason)`. Login + create/write permission required. Results go through `frappe.get_list`: User Permissions and field-level read permissions apply; a record the caller cannot read comes back as `restricted` with no ID or details. Which fields are shown is the rule's *Result Details* and fields flagged *Show in Results* — keep personal data (e.g. Employee phone / ID) out of them.

## Settings reference
Settings: enabled, live lookup, fuzzy threshold, results per lookup (1–25), scan limit, override roles, reason required. Rule: DocType, enabled, rule type, live lookup, strong action (Block/Warn), possible action (Warn/Block/Ignore), suggest similar names, result details, override roles, and field rows (Field, Kind, Match Role, Source = Document / Child Table / Linked Contact, Child Table, Group, Show in Results, Excluded). Excluded rows are kept but ignored. Invalid fieldnames are refused on save; a field removed from a DocType later is skipped, never fails a save.

Seeded rules (only fields the DocType really has; never overwritten): Item, Customer, Supplier, Employee, Contact, Address, Warehouse, Account, UOM, Brand, Manufacturer, Sales Partner, Territory, Lead, Opportunity, Purchase Invoice, Sales Invoice.

## Performance
Only configured fields are searched, with equality / `IN` lookups on ERPNext's own columns plus indexes added by `patches/v0_5_0/add_duplicate_indexes.py` (verify in `information_schema.statistics`, index names `zg_dup_*`); at most 200 candidates per lookup; results limited. Phone / ID values stored with spaces or dashes, and mid-name matches, need a scan — done only on tables under the *scan limit* (default 50 000 rows). Rules and settings are cached (no record data).

## Install / migrate
`bench --site <site> migrate` then `bench --site <site> clear-cache`. Migrate creates the DocTypes, seeds the rules (patch `seed_duplicate_rules`; fresh installs seed in `after_install`), stores the switch as on (`enable_duplicate_prevention_default_on`) and adds the indexes. Roll back: switch the app off, or untick *Enable Duplicate Prevention* in the Settings. Reload the Desk after a deploy (new JS).

## Files
New: `services/duplicate/{normalizers,config,matcher,enforcement,defaults,link_search}.py`, `api/v1/duplicate/lookup.py`, DocTypes `zg_duplicate_prevention_settings`, `zg_duplicate_rule`, `zg_duplicate_rule_field`, `zg_duplicate_role`, `zg_duplicate_override_log`, `public/js/zg_duplicate_lookup.js`, `public/css/zg_duplicate_lookup.css`, `patches/v0_5_0/*`, tests `tests/unit/test_duplicate_normalizers.py`, `tests/integration/test_duplicate_prevention.py`.
Modified: `hooks.py` (validate hook on the supported DocTypes; `search_link` override), `plugins/manifests/core_apps.py`, `zg_system_settings.json`, `services/ui_apps.py`, `install.py`, `patches.txt`, `translations/ar.csv`.

## Known limits
- The ad-hoc checks in `customer_sync_service._assert_no_duplicates` / `item_sync_service` still run first (their messages are what the mobile apps show); the engine backs them up. They were not replaced.
- Employee national ID: no such field exists in this app; add a custom field and a rule row if it is legally appropriate.
- Customer / Supplier mobile and e-mail are read from the document fields and linked Contacts; they are not editable on the Customer form itself (ERPNext fetches them from the primary Contact), so the live panel for them fires on Contact / Lead / quick-entry forms.
- Fuzzy matching looks at a bounded candidate set and is a suggestion only.
