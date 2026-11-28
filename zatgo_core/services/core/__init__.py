"""Shared foundation for every ZatGo module (Phase 3, docs/CORE_FRAMEWORK.md).

Only what more than one module needs and nothing yet provided lives here:

- `availability` -- is a ZatGo app or industry installed, enabled and licensed on this site (one answer, with reasons)
- `erpnext_api`  -- every call zatgo_core makes into ERPNext internals, in one place (upgrade risk C-02)
- `audit`        -- the one writer of Audit Log rows

Existing shared pieces stay where they are and are not wrapped again: `api/response.py` (API envelope),
`api/validators.py` (input and login checks), `services/idempotency.py` (idempotent create / submit),
`services/row_scope.py` and `permissions/` (record scope), `services/app_state.py` / `app_gate.py` (switches),
`utils/logging.py` (loggers), `install._run_steps` (setup steps).
"""
