# DocType catalog

*Phase 4, generated 2026-11-28 from the DocType JSON on `main` (after the `v0_6_0` rename). Regenerate with `scripts/doctype_catalog.py` rather than editing by hand.*

Column keys:
- **Kind**: regular, single (settings), child (table rows), submittable.
- **Naming**: the `autoname` rule.
- **Req**: mandatory fields.
- **Unique / Index**: database-level unique keys and search indexes.
- **Links**: Link targets.
- **Children**: child tables.
- **Roles**: roles in its DocPerms.
- **History**: `track_changes` (version history).
- **Hooks**: controller methods.
- **Refs**: files that name it outside its own folder (code / tests).

## Chat AI

| DocType | Kind | Naming | Fields | Req | Unique | Index | Links | Children | Roles | History | Hooks | Refs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AI Artifact | regular | `hash` | 8 | session, artifact_type | — | — | AI Chat Message, AI Chat Session, User | — | Chat AI Manager, Chat AI User, System Manager | no | — | 6 / 2 |
| AI Attachment | regular | `hash` | 11 | session, file_name | — | session | AI Chat Message, AI Chat Session | — | Chat AI Manager, Chat AI User, System Manager | no | — | 6 / 2 |
| AI Chat Memory | regular | `hash` | 4 | user | — | — | AI Chat Session, User | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 4 / 3 |
| AI Chat Message | regular | `hash` | 14 | session, role | — | session | AI Chat Session | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 10 / 5 |
| AI Chat Session | regular | `hash` | 8 | title, user | — | user | AI Conversation Summary, User | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 19 / 6 |
| AI Conversation Summary | regular | `hash` | 3 | session | — | — | AI Chat Session | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 5 / 4 |
| AI Integration Connector | regular | `hash` | 16 | service, label | — | — | — | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 4 / 2 |
| AI MCP Server | regular | `hash` | 13 | label | — | — | — | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 4 / 2 |
| AI Plugin Registry | regular | `hash` | 6 | app, plugin_name | — | — | — | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 1 / 1 |
| AI Provider Health Log | regular | `hash` | 6 | provider, checked_at | — | — | — | — | Chat AI Manager, System Manager | yes | — | 4 / 2 |
| AI REST Tool | regular | `field:tool_name` | 16 | tool_name, url_template | tool_name | — | — | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 4 / 2 |
| AI Scheduled Task | regular | `hash` | 18 | title, user, prompt, frequency | — | — | AI Chat Session, User | — | Chat AI Manager, Chat AI User, System Manager | no | — | 5 / 2 |
| AI Search Index | regular | `hash` | 12 | ref_doctype, ref_name | — | attachment, owner_user, session | AI Attachment, AI Chat Session, DocType, User | — | Chat AI Manager, System Manager | yes | — | 5 / 4 |
| AI Tool Log | regular | `hash` | 11 | tool_name | — | session, user | AI Chat Session, User | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 6 / 5 |
| AI Usage Daily | regular | `hash` | 10 | usage_date | — | usage_date, user | User | — | Chat AI Manager, Chat AI User, System Manager | yes | — | 6 / 4 |
| Chat AI Settings | single | `hash/prompt` | 89 | — | — | — | — | — | Chat AI Manager, System Manager | yes | — | 18 / 7 |

## Tracker

| DocType | Kind | Naming | Fields | Req | Unique | Index | Links | Children | Roles | History | Hooks | Refs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tracker Activity Session | regular | `naming_series:` | 13 | naming_series, user, status, activity_type | — | user, status, project, task | Activity Type, Company, Employee, Project +3 | — | System Manager, Tracker Worker | yes | — | 9 / 1 |
| Tracker Settings | single | `hash/prompt` | 2 | — | — | — | Activity Type, Company | — | System Manager, Tracker Top | yes | — | 8 / 3 |

## ZatGo Core

| DocType | Kind | Naming | Fields | Req | Unique | Index | Links | Children | Roles | History | Hooks | Refs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Application Registry | regular | `field:app_name` | 15 | app_name | app_name | — | — | — | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | validate | 2 / 0 |
| Application Settings | single | `hash/prompt` | 6 | — | — | — | — | Client Application | System Manager, ZatGo Application Admin, ZatGo Read Only | yes | validate | 5 / 0 |
| Audit Log | regular | `AUD-.YYYY.-.#####` | 12 | — | — | — | User | — | System Manager, ZatGo Application Admin, ZatGo Company Admin +1 | no | validate, on_trash | 6 / 6 |
| Branch Settings | regular | `format:BR-{company}-{#####}` | 16 | branch_name, company | — | — | Company, User, Warehouse | — | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | validate | 6 / 0 |
| Company Settings | regular | `field:company` | 28 | company | company | — | Account, Company, Cost Center, Currency +5 | — | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | validate | 10 / 12 |
| Config History | regular | `CFG-.YYYY.-.#####` | 8 | — | — | — | Registered Application, User | — | System Manager, ZatGo Application Admin, ZatGo Read Only | no | — | 1 / 1 |
| Config Profile | regular | `field:profile_name` | 5 | profile_name | profile_name | — | — | — | System Manager, ZatGo Application Admin | yes | — | 1 / 0 |
| Delivery Boy | regular | `field:code` | 12 | full_name, code | code | — | User, Vehicle | — | Delivery, Desk User, System Manager | yes | — | 9 / 2 |
| Device Token | regular | `hash` | 5 | user, token | token | user | User | — | All, System Manager | no | — | 4 / 2 |
| Duplicate Override Log | regular | `hash` | 6 | — | — | — | DocType, User | — | System Manager, ZatGo Application Admin | no | — | 3 / 1 |
| Duplicate Prevention Settings | single | `hash/prompt` | 7 | — | — | — | — | Duplicate Role | System Manager, ZatGo Application Admin | yes | validate, on_update | 3 / 1 |
| Duplicate Rule | regular | `field:ref_doctype` | 10 | ref_doctype | ref_doctype | — | DocType | Duplicate Role, Duplicate Rule Field | System Manager, ZatGo Application Admin, ZatGo Company Admin | yes | validate, on_update, on_trash | 3 / 0 |
| Edition | regular | `field:edition_id` | 22 | edition_id, edition_name | edition_id | — | — | Edition Feature | System Manager, ZatGo Application Admin, ZatGo Read Only | yes | validate, on_update, on_trash | 8 / 1 |
| Feature | regular | `field:feature_id` | 19 | feature_id, label, module | feature_id | — | Module | — | System Manager, ZatGo Application Admin, ZatGo Read Only | no | validate, on_trash | 4 / 0 |
| Feature Flag | regular | `field:flag_key` | 9 | flag_key, title, status | flag_key | — | Branch Settings, Company | — | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | validate | 2 / 0 |
| Gym Attendance | regular | `GYM-ATT-.#####` | 4 | membership, check_in | — | — | Gym Membership | — | System Manager, ZatGo Gym Manager, ZatGo Gym User | yes | validate | 2 / 0 |
| Gym Membership | regular | `GYM-MEM-.#####` | 11 | member, plan, company, start_date | — | — | Company, Customer, Gym Membership, Gym Plan +1 | — | System Manager, ZatGo Gym Manager, ZatGo Gym User | yes | validate | 4 / 1 |
| Gym Plan | regular | `field:plan_name` | 5 | plan_name, duration_days, price | plan_name | — | Item | — | System Manager, ZatGo Gym Manager, ZatGo Gym User | yes | validate | 5 / 2 |
| Integration Settings | single | `hash/prompt` | 31 | — | — | — | Email Account | — | System Manager, ZatGo Application Admin, ZatGo Read Only | yes | validate | 2 / 0 |
| KDS Ticket | regular | `hash` | 11 | title, item_name, qty | — | — | — | — | Desk User, System Manager | yes | — | 7 / 2 |
| Language Settings | single | `hash/prompt` | 1 | — | — | — | Language | — | System Manager, ZatGo Application Admin, ZatGo Company Admin | yes | — | 3 / 2 |
| Licence | regular | `field:payload_hash` | 28 | — | payload_hash | — | User | — | System Manager, ZatGo Application Admin, ZatGo Read Only | no | validate, on_trash | 6 / 5 |
| Licence History | regular | `field:licence_number` | 19 | licence_number | licence_number | — | User | — | System Manager | no | validate, on_trash | 4 / 0 |
| Metal Rate | regular | `JRATE-.#####` | 4 | metal, purity, rate_date, rate_per_gram | — | — | — | — | System Manager, ZatGo Jewellery Manager, ZatGo Jewellery User | yes | validate | 3 / 2 |
| Module | regular | `field:module_id` | 10 | module_id, label | module_id | — | — | — | System Manager, ZatGo Application Admin, ZatGo Read Only | no | validate, on_trash | 8 / 0 |
| MyBis Settings | single | `hash/prompt` | 21 | — | — | — | Company | — | System Manager, ZatGo Application Admin, ZatGo Company Admin | yes | validate | 2 / 2 |
| Number Series Settings | single | `hash/prompt` | 1 | — | — | — | — | Number Series Item | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | validate | 2 / 0 |
| Offline Sale Issue | regular | `format:OSI-{#####}` | 15 | client_id | client_id | — | Sales Invoice, User | — | Accounts Manager, System Manager, ZatGo Company Admin | yes | validate | 2 / 1 |
| Order | regular | `hash` | 24 | order_number | order_number, zatgo_client_id | — | Company, Customer, Delivery Boy, Payment Entry +3 | Order Item | Desk User, System Manager | yes | — | 7 / 6 |
| Payment Settings | single | `hash/prompt` | 13 | — | — | — | Account | — | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | — | 6 / 0 |
| Printer Settings | single | `hash/prompt` | 14 | — | — | — | — | — | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | — | 6 / 0 |
| Registered Application | regular | `field:app_key` | 13 | app_key, title | app_key | — | — | — | System Manager, ZatGo Application Admin, ZatGo Read Only | yes | — | 5 / 1 |
| Sales Invoice Naming Settings | single | `hash/prompt` | 4 | unmapped_user_behavior | — | — | Print Format | Sales Invoice Naming Rule | Accounts Manager, System Manager, ZatGo Invoice Naming Manager | yes | onload, validate | 5 / 0 |
| Service Ticket | regular | `hash` | 8 | title | — | — | — | — | Desk User, System Manager | yes | — | 5 / 1 |
| Setting Section | regular | `hash` | 13 | application, section_key, label | — | — | DocType, Registered Application, Setting Section | — | System Manager, ZatGo Application Admin, ZatGo Read Only | yes | validate | 2 / 1 |
| Storage Settings | single | `hash/prompt` | 19 | — | — | — | — | — | System Manager, ZatGo Application Admin, ZatGo Read Only | yes | — | 2 / 1 |
| Sync Settings | single | `hash/prompt` | 7 | — | — | — | — | — | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | — | 3 / 0 |
| Table | regular | `field:table_code` | 8 | table_code, table_name | table_code | — | Company, Order | — | Desk User, System Manager | yes | — | 19 / 4 |
| Theme Settings | single | `hash/prompt` | 3 | — | — | — | — | — | System Manager, ZatGo Application Admin, ZatGo Company Admin | yes | — | 3 / 3 |
| Trip | regular | `hash` | 18 | title | — | status, planned_at, sales_user | Customer, Sales Invoice, User, Vehicle +1 | — | System Manager, VanSale Admin, VanSale User | yes | — | 8 / 5 |
| User Preferences | regular | `field:user` | 9 | user | user | — | Language, User | — | All, System Manager | yes | — | 4 / 1 |
| Van Sale Profile | regular | `hash` | 17 | user | user | — | Account, User, Vehicle, Warehouse | Van Sale Profile Access | System Manager, VanSale Admin, VanSale User | yes | validate | 8 / 11 |
| VanSaleX Settings | single | `hash/prompt` | 16 | — | — | — | Account, Warehouse | VanSaleX Access | System Manager, VanSale Admin, VanSale User | yes | validate | 8 / 10 |
| ZatGo Delivery Stop | regular | `hash` | 31 | title | — | — | Delivery Boy | — | Delivery, Desk User, System Manager | yes | — | 7 / 5 |
| ZatGo Notification Settings | single | `hash/prompt` | 12 | — | — | — | — | — | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | — | 4 / 1 |
| ZatGo POS Settings | single | `hash/prompt` | 32 | — | — | — | Customer, Mode of Payment, Price List, Warehouse | — | System Manager, ZatGo Application Admin, ZatGo Company Admin | yes | onload, validate, on_update | 4 / 5 |
| ZatGo Security Settings | single | `hash/prompt` | 15 | — | — | — | — | — | System Manager, ZatGo Read Only | yes | validate | 3 / 2 |
| ZatGo System Settings | single | `hash/prompt` | 33 | — | — | — | Company, Cost Center, Country, Currency +3 | Enabled Industry | System Manager, ZatGo Application Admin, ZatGo Branch Admin +2 | yes | onload, validate, on_update | 15 / 16 |
| ZatGo Vehicle | regular | `field:plate` | 5 | title | — | — | — | — | Desk User, System Manager | yes | — | 5 / 3 |
| Client Application | child | `hash/prompt` | 12 | app_key, title, platform | — | — | — | — | — | no | — | 2 / 0 |
| Duplicate Role | child | `hash/prompt` | 1 | role | — | — | Role | — | — | no | — | 2 / 0 |
| Duplicate Rule Field | child | `hash/prompt` | 8 | fieldname, kind, match_role | — | — | — | — | — | no | — | 1 / 0 |
| Edition Feature | child | `hash/prompt` | 3 | feature | — | — | Feature | — | — | no | — | 1 / 0 |
| Enabled Industry | child | `hash/prompt` | 5 | industry | — | — | — | — | — | no | — | 1 / 0 |
| Number Series Item | child | `hash/prompt` | 6 | document_type, prefix | — | — | — | — | — | no | — | 2 / 0 |
| Order Item | child | `hash/prompt` | 8 | item_code, qty | — | — | Item | — | — | no | — | 3 / 0 |
| Payment Allocation | child | `hash/prompt` | 7 | mode_of_payment, account, amount | — | — | Account, Currency, Mode of Payment | — | — | no | — | 2 / 0 |
| Sales Invoice Naming Rule | child | `hash/prompt` | 9 | user, company, normal_series, return_series | — | — | Company, Print Format, User | — | — | no | — | 3 / 0 |
| Van Sale Profile Access | child | `hash/prompt` | 2 | access_key | — | — | — | — | — | no | — | 2 / 1 |
| VanSaleX Access | child | `hash/prompt` | 6 | access_key | — | — | — | — | — | no | — | 3 / 4 |
| ZatGo Mode of Payment Account | child | `hash/prompt` | 5 | company, account | — | — | Account, Company, Currency | — | — | no | — | 1 / 1 |

## ZatGo Space

| DocType | Kind | Naming | Fields | Req | Unique | Index | Links | Children | Roles | History | Hooks | Refs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Space Job Log | regular | `hash` | 6 | order, job_id | — | — | Space Order | — | System Manager | no | — | 2 / 1 |
| Space Order | regular | `naming_series:` | 14 | naming_series, slug, hostname, status +1 | hostname | — | Space Plan | Space Order App | System Manager | yes | — | 3 / 2 |
| Space Plan | regular | `field:code` | 8 | code, title, mock_price | code | — | — | — | All, System Manager | yes | — | 4 / 2 |
| Space Settings | single | `hash/prompt` | 2 | ram_pool_mb, disk_pool_mb | — | — | — | — | All, System Manager | yes | — | 6 / 3 |
| Space Order App | child | `hash/prompt` | 2 | app_package | — | — | — | — | — | no | — | 1 / 1 |
