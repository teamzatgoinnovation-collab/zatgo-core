# Core framework

*Phase 3, 2026-11-28. The shared foundation every ZatGo module uses. ADR-002: only what more than one module needs and nothing already provides. Everything listed under "Existing" was already in the app and is used as is, not wrapped again.*

## Map: the ten foundation components
| Component (brief) | Where | New in Phase 3? |
|---|---|---|
| 1. Common utilities | `utils/`, `api/validators.py` | no |
| 2. Shared validation | `api/validators.py` (`require_str`, `parse_json_*`, `parse_pagination`, `whitelist_filters`); `validation/` (settings validators) | no |
| 3. Error handling | `api/response.fail` (envelope); Frappe exceptions (`ValidationError`, `PermissionError`, `DoesNotExistError`) raised with `frappe.throw` | no |
| 4. Logging and audit | `utils/logging.get_logger(channel)`; **`services/core/audit.record`** | audit writer: **yes** |
| 5. Permission helpers | `api/validators.require_login` / `require_doc_permission`; `services/row_scope.py`; `permissions/` | no |
| 6. API response | `api/response.ok / fail / paginated` | no |
| 7. Document services | `services/idempotency.py` (`insert_idempotent`, `submit_or_rollback`, `find_by_client_id`); **`services/core/erpnext_api`** | ERPNext adapter: **yes** |
| 8. Configuration access | `services/app_state.py` (switches), area resolvers (`vansalex_settings.resolve*`, `pos_settings`, `ui_settings`), `services/settings_service.py` | `app_state.switch_on`: **yes** |
| 9. Module availability | **`services/core/availability`** | **yes** |
| 10. Installation and setup | `install._run_steps` + `setup/*` idempotent steps, `setup/deploy_check.py` | no |

## `services/core/availability`: is an app or industry on, and why not
```python
from zatgo_core.services.core import availability

availability.is_available("vansalex")      # True / False, same answer as app_state.is_on
availability.explain("restaurant")         # {"key", "kind", "known", "installed", "enabled", "licensed",
                                            #  "missing_requirements", "available", "reason"}
availability.summary()                     # every app and industry, for the hub, health checks, support
```
Layers:
- **known**: in the app catalog or the industry registry.
- **installed**: apps always; industries when implemented in this release.
- **enabled**: the switch or industry row.
- **licensed**: `licensing.gate`, which is always true while no licence is enforced.

`missing_requirements` lists dependencies that are off. They are reported, never switched on. Per-user authorization stays with roles, DocPerms and User Permissions; Phase 5 adds module roles.

**Use it** wherever you need *why* something is unavailable (an error message, the hub, a health check). For a plain gate, `app_state.is_on`, `app_gate.require_app` / `@app_api` and `industries.gate.require_industry` / `@industry_api` stay the API. They give the same answer, and the integration test checks that for every app and industry.

Supporting changes, both behaviour-preserving:
- `app_state.switch_on(key)`: the switch alone. `is_on` = `switch_on` and licensed.
- `industries.gate.switched_on_keys()`: ticked rows. `enabled_keys` = ticked, implemented and licensed.

## `services/core/erpnext_api`: calls into ERPNext internals
```python
from zatgo_core.services.core.erpnext_api import get_payment_entry, make_return_doc
from zatgo_core.services.core.erpnext_api import make_sales_invoice_from_quotation as make_sales_invoice
```
- Every ERPNext function zatgo_core calls (16 today: `TARGETS`) is wrapped once. Each wrapper imports its target at call time, so a test that patches the ERPNext function itself still works.
- **Rule**: no other module imports from `erpnext` (except `install.py`'s version check). `tests/unit/test_erpnext_api.py` enforces this, fails when a target disappears, and fails when a target stops accepting a keyword argument any caller passes.
- **Adding one**: add the target to `TARGETS` and a one-line wrapper, then import the wrapper.
- ERPNext classes that zatgo_core extends through `extend_doctype_class` are not wrapped.
- **On an ERPNext upgrade**: run `test_erpnext_api` first; a failure names the function and the argument.

## `services/core/audit`: the one Audit Log writer
```python
from zatgo_core.services.core import audit

audit.record("Theme Settings", name, "primary_color", old, new, reason="rebrand")
audit.record(DOCTYPE, edition_id, "import", None, summary_json, reason=..., strict=True)   # must not succeed silently
audit.record("Licence", name, "verify_failed", None, details, durable=True)               # survives the rollback
```
- Adds the user, date, time, IP address and browser of the request.
- A failed write is logged and the caller continues, unless `strict=True`.
- `durable=True` commits the row on its own inside a web request, for a refusal that is about to roll back.
- **Never pass a secret.** The settings mixin writes Password fields as `***`.
- Callers: `mixins/auditable.AuditableMixin` (settings field changes), `licensing/audit.log` (licence events), `licensing/editions._log_import`. These used to be three copies of the row-building code.

## Rules for new code
- **API handler**: `api/v1/<domain>/<file>.py`, thin. It validates input with `api/validators`, calls a service and returns through `api/response`. Gate it with `@app_api(key)` or `@industry_api(key)` under `@frappe.whitelist(methods=["POST"])` for writes.
- **Business logic** lives in `services/`. A financial create uses `idempotency.insert_idempotent` with the client's `zatgo_client_id`, and submits with `submit_or_rollback`. It never writes GL or stock rows.
- **ERPNext internals** only through `services/core/erpnext_api`.
- **Config** only through its resolver (`app_state`, `vansalex_settings`, `pos_settings`, ...). Never read `ZatGo System Settings` switches directly.
- **Record scope** in SQL through `services/row_scope`; otherwise `frappe.get_list`, which applies User Permissions. Avoid `frappe.get_all`, which skips them.
- **Audit** through `services/core/audit`.
