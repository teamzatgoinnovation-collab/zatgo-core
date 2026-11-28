# ZatGo permissions

*Phase 8, 2026-11-28.*

## Principle
**Visibility is not security.** Hiding a workspace, link or button (Module Settings, workspace roles) only tidies the screen. Every refusal is made on the server, by Frappe's permission engine or by a check in a ZatGo service, so it holds for Desk, REST (`/api/resource`), lists, reports, exports and the ZatGo API alike.

ZatGo uses Frappe's own model and adds nothing parallel to it:

| Layer | Frappe mechanism | Where ZatGo uses it |
|---|---|---|
| Who may use a DocType | Role permissions (DocPerm / Custom DocPerm) | ERPNext's standard roles; ZatGo DocTypes ship their own perms |
| Which records | User Permissions (`applicable_for`, apply to all DocTypes) | Company, Warehouse, Item Group, Item, Customer (`restrict_user`) |
| Owner-only records | `has_permission` + `permission_query_conditions` hooks | ZatGo Delivery Stop (a courier sees only their stops) |
| A switched-off module | `has_permission "*"` hook + API gate | `module_settings.doc_has_permission`, `module_settings.gate_api` |
| A bundle of roles | Role Profile | the personas below |

## Personas (Role Profiles)
Created once by `setup/ensure_role_profiles.py` on install/migrate. After that they belong to the site: an administrator may change them in Desk and they are never reset.

| Profile | Roles | Typical limits (User Permissions) |
|---|---|---|
| ZatGo Sales User | Sales User | Company, Customer |
| ZatGo Sales Manager | Sales Manager, Sales User | Company |
| ZatGo Purchase User | Purchase User | Company |
| ZatGo Stock User | Stock User | Company, Warehouse |
| ZatGo Restricted Stock User | Stock User | Item Group and Warehouse (for example: only frozen items, only the cold store) |
| ZatGo Accountant | Accounts User | Company |
| ZatGo Administrator | System Manager, ZatGo Application Admin | — |

Record limits in one call (System Manager only):

```
bench --site X execute zatgo_core.setup.ensure_role_profiles.restrict_user \
    --kwargs "{'user': 'cold@example.com', 'item_groups': ['Frozen'], 'warehouses': ['Cold Store - ZTC']}"
```

## ZatGo code that reads records directly
Code that uses `frappe.get_all` (no permission check) must apply User Permissions itself, through `services/row_scope.py`:
- `permitted_values(allow, for_doctype)` — the values a user is limited to, or `None` when unrestricted.
- `narrow(values, allow, for_doctype)` — keep only the permitted ones.

Fixed in Phase 8:
- POS stock list (`resto_pos_admin_service._stock_rows`) honours Warehouse, Item Group and Item permissions.
- POS customer list (`list_customers`) uses `frappe.get_list`.
- Delivery stops: owner rule moved from the API alone into hooks (`permissions/delivery_scope.py`), so Desk and REST apply it too.

## Tests
- `tests/permissions/test_role_matrix.py` — the ZatGo role matrix.
- `tests/permissions/test_personas.py` — each persona: allowed and refused actions, a restricted stock user's lists and POS stock, reports, the ZatGo API.
- `tests/integration/test_delivery_stop_access.py` — couriers on every route.
- `tests/integration/test_settings_management.py` — Company Settings reads honour Company permissions.

## Known gaps (later phases)
- About 140 GET-callable endpoints change data (S-03, Phase 12).
- Other `frappe.get_all` reads in ZatGo services are listed in `SECURITY_AUDIT.md`; each is reviewed when its module is touched.
