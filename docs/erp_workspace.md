# ZatGo ERP workspace and the "ZG Accounts & Inventory" role

**What it is.** One workspace, **ZatGo ERP** (heading *Accounts & Inventory*), for everyday accounting and stock work.
Every link opens ERPNext's own screen; nothing is duplicated.

```
Sidebar:  Home, Dashboard (ERPNext "Accounts" dashboard)
Transactions  Sales Invoice, Purchase Invoice, Sales Order, Purchase Order, Payment Entry, Payment Reconciliation
Setup         Item, Customer, Supplier, Warehouse
Reports       Profit and Loss Statement, Balance Sheet, Trial Balance, General Ledger, Stock Ledger,
              Business Summary Report, Sales Register, Purchase Register
Settings      Accounts, Stock, Buying, Selling, Print, System
```
The first four Transactions are also quick-open shortcuts at the top of the Home page.

**Who sees it.** Users with the role **ZG Accounts & Inventory** (and System Manager). Give a user the role to give them
the workspace; no ERPNext role is needed on top of it.

**What the role may do** (`setup/ensure_erp_perms.py`, least privilege, no cancel / delete):
- Transactions: read, write, create, submit, print, email, report, export.
- Setup masters: read, write, create, print, report, export. Address, Contact, Item Price: read, write, create.
- Reports: the eight reports above (a Custom Role row per report keeps each report's own roles and adds this one);
  GL Entry, Stock Ledger Entry, Bin: read, report, export.
- Settings: read only. Company, Account, price lists, taxes and similar lookups: read only.

Rights are seeded once per DocType / report (same rules as VanSale: an administrator's later change is kept).

**How it is installed.** `ensure_core_desk()` (install and every migrate) imports the Workspace file
(`zatgo_core/workspace/zatgo_erp/zatgo_erp.json`), builds the *ZatGo ERP* sidebar and the Apps-screen icon, and
`ensure_roles()` / `ensure_erp_perms()` create the role and its rights. Repeating install or migrate changes nothing.

**Changing it.** Edit `SECTIONS` in `zatgo_core/services/erp_workspace.py`, bump `WORKSPACE_MODIFIED`, run
`python3 scripts/build_zatgo_erp_workspace.py`, commit the regenerated JSON (a unit test fails if it is stale), then
`bench migrate` on each site. A site's existing copy of the workspace is replaced only when `WORKSPACE_MODIFIED` is newer.
