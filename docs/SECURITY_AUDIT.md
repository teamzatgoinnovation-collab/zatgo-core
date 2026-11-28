# Security audit

*Phase 1, 2026-11-28, `main` at `d5bc17b`. Evidence and severity keys as in `TECHNICAL_AUDIT.md`. No CRITICAL finding.*

## Findings
| ID | Sev | File / module | Existing → problem | Impact / risk | Recommendation | Prio | Evidence |
|---|---|---|---|---|---|---|---|
| S-01 | HIGH | Accounting money endpoints: `erpnext_writes.py` (Sales Invoice, Payment Entry, return, Journal Entry); `create_sales_invoice_from_quotation` | `client_id` is optional, so a retried request posts a second payment or invoice; invoice-from-quotation has no already-converted check. | Duplicate money documents. | Make `client_id` required on money endpoints (older clients get a clear error); check the Quotation's existing invoice. | P1 | Carried 11-06 (read) |
| S-02 | HIGH | Replay paths: `vansalex_service.py` Sales Order, return, collection, Stock Entry | An idempotent replay acknowledges cancelled or draft documents and never compares the payload. | The client believes a sale or collection exists when it was cancelled. | Apply the Sales Invoice checks (`_ensure_submitted_sales_invoice`, Retail's `_check_replay`) to every replay. | P1 | Carried 11-06 |
| S-03 | MED | 136 whitelisted methods with write-like names and no `methods=` | Mutations reachable by GET. A session cookie plus a crafted GET is CSRF-prone (Frappe checks CSRF on POST). | Unwanted writes through a link. | `methods=["POST"]` module by module, with each client checked (Resto POS done 11-06; MyBis keeps GET deliberately). Largest: accounting 49, tracker 21, vansalex 15. | P2 | Read |
| S-04 | MED | `permissions/guards.py::can_access`, `settings_service.save_doc` | Settings access by role only; Company and Branch Admins reach any company's or branch's settings; `save_doc` updates any field. | One company admin can change another company's defaults. | Scope by User Permission on Company/Branch; allow-list writable fields per settings DocType. | P2 | Read |
| S-05 | MED | POS offline sales: `retail_pos_service.py`, `offline_sale.py` | Where the site allows offline sales, any cashier can send `offline=1` and skip the price floor and discount cap, and back-date. | Price and discount abuse. | Require a role or registered device for offline; keep the caps; flag every offline sale for review. | P2 | Carried 11-06 |
| S-06 | MED | `chat_ai/api/chat.py::_assert_session_access` | Chat AI Manager and System Manager read, export or delete any user's conversation. | Privacy: conversations can include business data. | Manager access read-only and audited, or opt-in per conversation. | P2 | Read |
| S-07 | MED | `zg_integration_settings.firebase_credentials_json` | A plaintext Code field. | Service-account key readable by settings readers and in backups. | Password field or site_config; no Python reads it today, so it may be removable. | P2 | Read |
| S-08 | MED | MyBis `services/mybis/queries.guard` | Refuses users with non-Company User Permissions, but not `if_owner` or permission-query restrictions. | A user limited to their own documents sees company totals. | Require unrestricted read, or a manager role, for MyBis. | P2 | Carried 11-06 |
| S-09 | MED | `services/mybis` and reports: `frappe.get_all` / raw SQL after a DocType check | POS customer list (`resto_pos_admin_service.list_customers`) and other reads skip User Permissions. | Data outside a user's company or territory. | `get_list` or `services/row_scope`. | P2 | Carried 11-06 |
| S-10 | MED | Tracker `add_member`, `hierarchy` | Saves with `ignore_permissions`; a Team Lead can add any existing non-Employee user; `org_tree` lists everyone when company is empty. | Privilege and role spread inside Tracker. | Check project access; restrict who can be added. | P2 | Carried 11-06 |
| S-11 | MED | ZatGo Space `_assert_internal_token` | `!=` comparison; token accepted in the query string (logged). | Timing leak; token in logs. | `hmac.compare_digest`; header only. | P2 | Read |
| S-12 | MED | Delivery | POD OTP stored, never checked; the ownership check is in the API, not on `/api/resource` or the form. | Proof of delivery can be faked. | Verify OTP; a `has_permission` hook for ZG Delivery Stop. | P3 | Read |
| S-13 | LOW | `overrides/print_entry.download_pdf` (`allow_guest=True`) | Same as Frappe's own (shared print links); looks up the Sales Invoice company before Frappe's permission check. | Nothing returned to the caller. | Keep; check permission first. | P3 | Read |
| S-14 | LOW | `print_tracking.get_copy_label` | Any reader with `trigger_print` bumps the counter with a raw UPDATE on a submitted document. | "DUPLICATE COPY" label can be flipped by readers. | Count only for print-permitted users. | P3 | Carried 11-06 |
| S-15 | LOW | Chat AI model endpoints | `openai_compat.py` and `web_search.py` use plain `urlopen` (redirects followed, no IP pinning). | An admin-set "local" URL could redirect off-network. | Reuse `tool_sources/net.request`. | P3 | Carried 11-06 |
| S-16 | INFO | `health.ping` guest | Returns the version. | Version disclosure. | Drop the version for guests. | P3 | Read |

## Checked and sound
- Six `allow_guest` methods only: ping, four Space wizard endpoints (rate-limited), PDF download.
- No hardcoded credentials; no TLS bypass; no `eval`/`exec`.
- SQL values are bound. Interpolated identifiers in MyBis are reviewed by a test. Three f-string SQL sites interpolate code-owned names only.
- Gates fail closed. App switching is System Manager only, enforced in the controller.
- The Chat AI tool network guard pins addresses and refuses redirects and metadata IPs.
- Licensing: signed licences with Ed25519, private key outside the repo, append-only audit log.
- The subscription and licence state live in site_config, which site admins can't write.

## Permission model risk (important for Phases 5, 6 and 8)
- **Custom DocPerm semantics.** Once a DocType has any Custom DocPerm, Frappe ignores its standard rows. The 11-06 fix copies them first. Every future seeding must keep that rule.
- **Visibility is separate from security today.** Sidebars and the folder hide; gates, hooks and DocPerms decide. Keep it that way, and test both (Phase 8).
