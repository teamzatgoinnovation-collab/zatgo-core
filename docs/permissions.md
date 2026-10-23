# Permission Matrix — ZatGo Core

## Roles

| Role | Purpose |
|------|---------|
| System Manager / Administrator | Full control |
| ZG Company Admin | Company + branch settings, read audit |
| ZG Branch Admin | Branch settings write, limited reads |
| ZG Application Admin | Apps, feature flags, integrations |
| ZG Read Only | Read settings / audit / reports |
| Delivery | Delivery app login — linked `ZG Delivery Boy.user`; read/write own stops |
| ZG Invoice Naming Manager | Edit `ZG Sales Invoice Naming Settings` (which series each user's invoices/returns get). System Manager and Accounts Manager can too; nobody else, including Sales/VanSale users, can read it |

## Who can switch apps and industries

**System Manager (and Administrator) only**, on every route. The switches are fields of `ZG System Settings`,
which `ZG Company Admin` and `ZG Application Admin` can otherwise edit — so the DocType controller itself
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

`ZG Device Token` and `ZG User Preferences` belong to their `user`: list, read, write and create are limited
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

`ZG Delivery Boy`, `ZG Delivery Stop`, `ZG Vehicle`, `ZG Service Ticket`, `ZG Order`, `ZG Table`, `ZG KDS Ticket`
grant read/write/create to `Desk User` (every System User) -- not to `All`, which includes portal users. Which
staff role may do what per product (cashier vs. kitchen vs. dispatcher) is a product decision still to be made.

## DocType permission query

- `ZG Company Settings` → `company_permission_query` restricts by User Permission on Company.

## Audit immutability

- `ZG Audit Log` is create/read for managers; delete restricted to System Manager in controller.
