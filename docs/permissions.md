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

## DocType permission query

- `ZG Company Settings` → `company_permission_query` restricts by User Permission on Company.

## Audit immutability

- `ZG Audit Log` is create/read for managers; delete restricted to System Manager in controller.
