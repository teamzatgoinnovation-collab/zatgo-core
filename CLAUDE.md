# zatgo-core

Custom Frappe app extending ERPNext for ZatGo's Van Sales / Accounting / Inventory platform. See `../../CLAUDE.md` (workspace root) for full multi-repo context, git/deploy workflow, and local dev bench setup — this file only covers what's specific to this repo.

## Non-negotiables

- Never write GL/stock ledger data directly — always go through ERPNext's own document controllers (`frappe.get_doc({...}).insert()` / `.submit()`). Every existing service in `zatgo_core/services/` (`go_van_service.py`, `erpnext_writes.py`) follows this; keep it that way.
- New create-endpoints for financial documents (Sales Invoice, Payment Entry, Stock Entry, and their returns) must use `zatgo_core.services.idempotency.insert_idempotent` rather than a bare `doc.insert()`, so a concurrent duplicate `zatgo_client_id` resolves to a clean idempotent response instead of a raw DB error.
- New custom fields that are load-bearing for correctness (uniqueness constraints, sync keys) must be created from `install.py`'s `after_install`/`after_migrate` (via `zatgo_core/setup/ensure_custom_fields.py`), not solely from a `patches.txt` entry — patches have been observed to silently no-op inside `bench install-app`'s bundled pipeline even though Patch Log records them as successful. Verify with a raw `information_schema` query after any change to this area, don't trust the patch log.
- Test with `bench --site <site> run-tests --app zatgo_core` (needs `allow_tests` config set first) before considering a change done. Existing integration tests in `zatgo_core/tests/integration/` cover the VanSale order/return/collection money-path and idempotency — extend them, don't bypass them.

## Known pre-existing issue (not yet fixed, don't be confused by it)

`zatgo_core/tests/unit/test_app_import.py::test_package_version` asserts `__version__ == "0.2.0"` but `hooks.py` has `app_version = "0.2.2"` — stale assertion, unrelated to whatever you're working on unless you're specifically asked to fix it.
