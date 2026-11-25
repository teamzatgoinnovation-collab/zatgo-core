# ZatGo ERP workspace and the "ZatGo Accounts & Inventory" role

**What it is.** One workspace, **ZatGo ERP** (heading *Accounts & Inventory*), for everyday accounting and stock work.
Every link opens ERPNext's own screen; nothing is duplicated.

```
Sidebar:  Home, Dashboard ("ZatGo ERP Dashboard": our Number Cards + ERPNext's accounting and stock charts and cards)
Transactions  Sales Invoice, Purchase Invoice, Sales Order, Purchase Order, Payment Entry, Payment Reconciliation
Setup         Item, Customer, Supplier, Warehouse
Reports       Profit and Loss Statement, Balance Sheet, Trial Balance, General Ledger, Stock Ledger,
              Business Summary Report, Sales Register, Purchase Register
Settings      Accounts, Stock, Buying, Selling, Print, System
```

## Add a DocType, Page or Report (no code, no deploy)
1. Open **ZatGo ERP**, click **⋯ → Edit**.
2. In the card you want (Transactions, Setup, Reports, Settings) add a link: DocType, Page or Report. Or add a new card.
3. **Save.** The sidebar is rebuilt from the workspace at once (`services/app_sidebar.py`, hooked on Workspace save), the same
   way as every other ZatGo app: *Home*, *Dashboard*, then one group per card. Removing a link removes it from the sidebar.

A link only shows for a user who may open it. If the new DocType / Report is not listed for people who hold only the role
**ZatGo Accounts & Inventory**, give that role the right (Role Permission Manager). Staff with ERPNext's own roles already have
theirs.

To add a **Number Card** or chart: Edit the workspace (or the **ZatGo ERP Dashboard**) and add a card / chart widget;
Frappe's Number Card is the editable standard one. Shipped cards (`ZatGo Sales Invoices`, `ZatGo Sales Invoice Total`, and the same
for Purchase Invoice, Sales Order, Purchase Order = 8) count submitted documents and sum their Grand Total, and sit on the
Dashboard. They follow header-level User Permissions (company, customer, warehouse...); item-group limits are applied only by
the summary block on the home page.

The **workspace is the site's own**: a release never overwrites it. New default items shipped in a later release are added once
(`ensure_default_items()` in `services/erp_workspace.py`, a marker per item), never removed or reordered; an item you deleted
stays deleted.

## The home page
At the top, one tile per Sales Invoice, Purchase Invoice, Sales Order and Purchase Order shows **how many submitted documents and
their Grand Total** (click to open the list), with a period switch (All time / This year / This month; remembered in the
browser). Below: the **top selling product** and the **top category** (net amount over submitted Sales Invoices, the next four
listed underneath). **User Permissions are respected:** a user restricted to Item Groups / Items (or to customers, warehouses...)
sees only those documents and items; their totals are then the net amount of the lines they may see. Source:
`services/erp_summary.py`, API `zatgo_core.api.v1.erp_summary.get`, drawn by the Custom HTML Block "ZatGo ERP Summary"
(`templates/erp_summary/`, refreshed on every migrate).

The Dashboard has its own name on purpose: Frappe chooses the sidebar from the last part of the page address, and
`dashboard-view/Accounts` would switch to ERPNext's own "Accounts" sidebar and leave this one. It is a *Dashboard shortcut* in the
workspace (it must stay a block on the page, or Frappe's editor drops it) and ships as
`zatgo_core/zatgo_core_dashboard/zatgo_erp_dashboard/`.

## Who sees it
The workspace and its Apps-screen icon are open to **ZatGo Accounts & Inventory**, System Manager and ERPNext's working roles
(Accounts, Sales, Purchase, Stock and Manufacturing users and managers), so existing staff see it without any change. Each person
still sees only the links their own document rights allow. **ZatGo Accounts & Inventory** is the role that *grants* the rights below:
give it to a user who has none of the ERPNext roles. A user whose **Default Workspace** (User form → Settings) is ZatGo ERP
opens it from a bare `/desk`.

**What the role may do** (`setup/ensure_erp_perms.py`, least privilege, no cancel / delete):
- Transactions: read, write, create, submit, print, email, report, export.
- Setup masters: read, write, create, print, report, export. Address, Contact, Item Price: read, write, create.
- Reports: the eight reports above (a Custom Role row per report keeps each report's own roles and adds this one);
  GL Entry, Stock Ledger Entry, Bin: read, report, export.
- Settings: read only. Company, Account, price lists, taxes and similar lookups: read only.

Rights are seeded once per DocType / report (same rules as VanSale: an administrator's later change is kept).

## How it is installed (for developers)
`ensure_core_desk()` (install and every migrate) imports the Workspace file (`zatgo_core/workspace/zatgo_erp/zatgo_erp.json`) if the
site has none, adds missing default items, builds the *ZatGo ERP* sidebar from the workspace, repairs the Apps-screen icon, and
`ensure_roles()` / `ensure_erp_perms()` create the role and its rights. Repeating install or migrate changes nothing.

**Changing the defaults** (for new sites and as add-once items for existing ones): edit `SECTIONS` (or the dashboard / cards) in
`zatgo_core/services/erp_workspace.py`, run `python3 scripts/build_zatgo_erp_workspace.py`, commit the regenerated files (a unit
test fails if they are stale). Do **not** bump `WORKSPACE_MODIFIED`: a newer file overwrites the site's workspace. The dashboard and
number-card files are code-owned: bump `DASHBOARD_MODIFIED` / `NUMBER_CARDS_MODIFIED` to roll a change out, then `bench migrate`.
