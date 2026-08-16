# zatgo-core

Custom Frappe app extending ERPNext for ZatGo's Van Sales / Accounting / Inventory platform. See `../CLAUDE.md` (Frappe/ERPNext category) and `../../.claude/rules/` (git, testing, accounting, architecture, security) for everything not specific to this repo.

## Repo-specific pointers

- Idempotent-insert helper: `zatgo_core/services/idempotency.py::insert_idempotent`. Use it for any new create-endpoint keyed on `zatgo_client_id` rather than re-deriving the check-then-insert pattern.
- Custom-field self-healing: `zatgo_core/setup/ensure_custom_fields.py`, called from `install.py`'s `after_install`/`after_migrate`. If you add a new schema-critical custom field, register it there too, not only in a `patches.txt` entry.
- Integration tests live in `zatgo_core/tests/integration/` (money-path, returns, idempotency) — extend these for new financial-document endpoints rather than relying on unit tests alone.

## Known pre-existing issue (not fixed, don't be confused by it)

`zatgo_core/tests/unit/test_app_import.py::test_package_version` asserts `__version__ == "0.2.0"` but `hooks.py` has `app_version = "0.2.2"` — stale assertion, unrelated to whatever you're working on unless specifically asked to fix it.
