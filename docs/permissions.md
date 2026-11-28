# Permission Matrix — ZatGo Core

## Roles

| Role | Purpose |
|------|---------|
| System Manager / Administrator | Full control |
| ZatGo Company Admin | Company + branch settings, read audit |
| ZatGo Branch Admin | Branch settings write, limited reads |
| ZatGo Application Admin | Apps, feature flags, integrations |
| ZatGo Read Only | Read settings / audit / reports |
| Delivery | Delivery app login — linked `Delivery Boy.user`; read/write own stops |
| ZatGo Invoice Naming Manager | Edit `Sales Invoice Naming Settings` (which series each user's invoices/returns get). System Manager and Accounts Manager can too; nobody else, including Sales/VanSale users, can read it |

## Who can switch apps and industries

**System Manager (and Administrator) only**, on every route. The switches are fields of `ZatGo System Settings`,
which `ZatGo Company Admin` and `ZatGo Application Admin` can otherwise edit — so the DocType controller itself
(`services/app_authority.py`, called from `validate`) refuses a save that changes an app switch or the
Industries table unless the user is a System Manager. The Desk form, the REST API and the **ZatGo Apps** page
are all bound by the same rule. Install, migrate and patches (system code) are exempt. Other settings on the
same form stay editable by the roles below.

## Category matrix (service guards)

| Category | System Manager | Company Admin | Branch Admin | Application Admin | Read Only |
|----------|----------------|---------------|--------------|-------------------|-----------|
| system | RW | — | — | — | R* |
| company | RW | RW | — | — | R* |
| branch | RW | RW | RW | — | R* |
| security | RW | — | — | — | R |
| integrations | RW | — | — | RW | R |
| features | RW | — | — | RW | R |
| apps | RW | — | — | RW | R |
| audit | RW | R | R | R | R |

\* DocType JSON also grants Read Only role read on most settings forms.

The caller never chooses the category: `save_settings` derives it from the DocType and only accepts the ZatGo
settings DocTypes; `seed_bundled_manifests`, `export_settings` and `get_dashboard` need System Manager /
Application Admin (read-only roles can read the registry but not re-seed it).

## Per-user DocTypes

`Device Token` and `User Preferences` belong to their `user`: list, read, write and create are limited
to the owner on every route (`permissions/owner_scope.py`, `permission_query_conditions` + `has_permission`),
so nobody can read another user's push tokens or register a token under someone else. System Manager sees all.
The hub's own server code (`devices.register_token`, …) runs with `ignore_permissions` and checks ownership
itself.

## Row-level scope of API reads

`services/row_scope.py`: list/report endpoints that cannot use `frappe.get_list` (ledger and trial-balance SQL) add
the user's Company User Permission to their SQL; the rest read with `get_list`, so User Permissions and
`permission_query_conditions` apply. A portal (Website User) session sees only the Sales Orders / Purchase Orders
of its own Customer / Supplier (ERPNext Portal User links). Administrator and users without a Company User
Permission see what they always saw.

## Staff-only DocTypes

`Delivery Boy`, `ZatGo Delivery Stop`, `ZatGo Vehicle`, `Service Ticket`, `Order`, `Table`, `KDS Ticket`
grant read/write/create to `Desk User` (every System User) -- not to `All`, which includes portal users. Which
staff role may do what per product (cashier vs. kitchen vs. dispatcher) is a product decision still to be made.

## DocType permission query

- `Company Settings` → `company_permission_query` restricts by User Permission on Company.

## Audit immutability

- `Audit Log` is append-only (controller): entries are written by the system only (a Desk / REST insert is refused), never changed; delete needs System Manager, and licensing entries cannot be deleted (`docs/licensing.md`).

---

## Access model and personas (Phase 8)

*Phase 8, 2026-11-28.*

### Principle
**Visibility is not security.** Hiding a workspace, link or button (Module Settings, workspace roles) only tidies the screen. Every refusal is made on the server, by Frappe's permission engine or by a check in a ZatGo service, so it holds for Desk, REST (`/api/resource`), lists, reports, exports and the ZatGo API alike.

ZatGo uses Frappe's own model and adds nothing parallel to it:

| Layer | Frappe mechanism | Where ZatGo uses it |
|---|---|---|
| Who may use a DocType | Role permissions (DocPerm / Custom DocPerm) | ERPNext's standard roles; ZatGo DocTypes ship their own perms |
| Which records | User Permissions (`applicable_for`, apply to all DocTypes) | Company, Warehouse, Item Group, Item, Customer (`restrict_user`) |
| Owner-only records | `has_permission` + `permission_query_conditions` hooks | ZatGo Delivery Stop (a courier sees only their stops) |
| A switched-off module | `has_permission "*"` hook + API gate | `module_settings.doc_has_permission`, `module_settings.gate_api` |
| A bundle of roles | Role Profile | the personas below |

### Personas (Role Profiles)
Built only from ERPNext's standard roles: no Custom DocPerm is added, because a custom row makes Frappe ignore the standard ones. Created once by `setup/ensure_role_profiles.py` on install/migrate. After that they belong to the site: an administrator may change them in Desk and they are never reset.

| Profile | Roles | Typical limits (User Permissions) |
|---|---|---|
| ZatGo Sales User | Sales User (quotations, sales orders; ERPNext gives invoicing to Accounts User) | Company, Customer |
| ZatGo Sales Manager | Sales Manager, Sales User | Company |
| ZatGo Purchase User | Purchase User | Company |
| ZatGo Stock User | Stock User | Company, Warehouse |
| ZatGo Restricted Stock User | Stock User | Item Group and Warehouse (for example: only frozen items, only the cold store) |
| ZatGo Accountant | Accounts User (sales and purchase invoices, payments, journals) | Company |
| ZatGo Administrator | System Manager, ZatGo Application Admin and every ERPNext manager role: all Desk apps, like the Administrator user, not only ZatGo ERP | — |

Record limits in one call (System Manager only):

```
bench --site X execute zatgo_core.setup.ensure_role_profiles.restrict_user \
    --kwargs "{'user': 'cold@example.com', 'item_groups': ['Frozen'], 'warehouses': ['Cold Store - ZTC']}"
```

### ZatGo code that reads records directly
Code that uses `frappe.get_all` (no permission check) must apply User Permissions itself, through `services/row_scope.py`:
- `permitted_values(allow, for_doctype)` — the values a user is limited to, or `None` when unrestricted.
- `narrow(values, allow, for_doctype)` — keep only the permitted ones.

Fixed in Phase 8:
- POS stock list (`resto_pos_admin_service._stock_rows`) honours Warehouse, Item Group and Item permissions.
- POS customer list (`list_customers`) uses `frappe.get_list`.
- Delivery stops: owner rule moved from the API alone into hooks (`permissions/delivery_scope.py`), so Desk and REST apply it too.

### Tests
- `tests/permissions/test_role_matrix.py` — the ZatGo role matrix.
- `tests/permissions/test_personas.py` — each persona: allowed and refused actions, a restricted stock user's lists and POS stock, reports, the ZatGo API.
- `tests/integration/test_delivery_stop_access.py` — couriers on every route.
- `tests/integration/test_settings_management.py` — Company Settings reads honour Company permissions.

### Known gaps (later phases)
- About 140 GET-callable endpoints change data (S-03, Phase 12).
- Other `frappe.get_all` reads in ZatGo services are listed in `SECURITY_AUDIT.md`; each is reviewed when its module is touched.
