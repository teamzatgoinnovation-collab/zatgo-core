# ZatGo Desk: workspaces and navigation

*Phase 6, 2026-11-28.*

## What a user sees
| Entry on the Apps screen | What it is | Defined in |
|---|---|---|
| **ZatGo ERP** (home: Accounts & Inventory) | summary block, dashboard, the everyday accounting and stock links | `services/erp_workspace.py`, `workspace/zatgo_erp/` |
| **ZatGo Sales**, **Purchase**, **Stock**, **Accounting**, **Production**, **Quality**, **Service**, **HR**, **Reports** | one workspace per module: number cards, quick actions ("New Sales Invoice", ...), cards of links, area reports | `services/module_workspaces.py` (`SPECS`) |
| **ZatGo** (folder) | every ZatGo app that is on, plus General Settings | `events/boot.py`, `services/core_sidebar.py` |
| ZatGo apps (VanSaleX, POS, AI, Tracker, ...) | each app's own workspace and sidebar | `<module>/app_manifest.py`, `services/app_sidebar.py` |

Every link opens ERPNext's own screen; ZatGo adds navigation, not copies of ERPNext forms or reports.

## Who sees which workspace
1. **Module enabled** (Module Settings → Enabled) **and Show in Navigation** ticked. Otherwise the workspace, its sidebar and its Apps-screen icon are hidden.
2. **Roles**: each workspace and icon list their area's ERPNext roles (Sales User, Stock User, ...) plus System Manager. Frappe shows them only to users with one of those roles.
3. **Document rights**: inside a workspace, Frappe hides each link the user may not open.

**Visibility is not security.** "Show in Navigation" only hides; an enabled module keeps working through its documents and APIs. Switching a module **off** (Enabled) is what refuses its ZatGo APIs and ZatGo DocType writes (`MODULE_DEPENDENCIES.md`).

## Configuring a customer site (no code, no per-site edits)
Open **ZatGo → Modules (on / off)** (Module Settings):

| Customer | Set |
|---|---|
| A: Sales only (Customer, Item, Sales Invoice) | untick *Show in Navigation* for every module except Sales. Stock and Accounting stay **enabled**, because a sale posts through them. |
| B: Sales, Purchase, Stock, Reports | untick *Show in Navigation* for Accounting, Production, Quality, Service and HR; untick *Enabled* for Production, Quality and Service if they are not used at all |
| C: Sales, Purchase, Stock, Accounting, Production | untick *Show in Navigation* (or *Enabled*) for Quality, Service and HR |

Per user, on top of that:
- the user's **roles** decide which of the visible workspaces they get.
- **User Permissions** (Company, Warehouse, Item Group) decide which records they see.
- Frappe's own **Default Workspace** (User → Settings) chooses where they land.
- Each user can still hide icons on their own Apps screen (Frappe Desk).

## How it is built and kept
- **Created once.** `module_workspaces.ensure()` (install and every migrate) creates a module's workspace if it is missing. It adds only links whose DocType or Report exists on the site; for example, HR needs the `hrms` app, and a module whose app is not installed gets no workspace. After that the workspace is the site's: an administrator may edit it in Desk, and its sidebar follows (`Workspace.on_update`).
- **Visibility** is re-applied on every migrate and on every Module Settings save (`sync_visibility`): the Workspace's `is_hidden`, its sidebar (synced empty while hidden), and its Desktop Icon's `hidden`. Nothing is ever deleted.
- **Adding a module workspace**: add a `Spec` to `SPECS`, using the licensing module id, ERPNext DocTypes and Reports and roles of that area. Only existing ones are used.
- **Workspaces made in code carry no `module`/`app`** (Frappe's migrate deletes such public workspaces as orphans). Their sidebars do carry them.

## Not provided
"Recently accessed items" has no native Frappe workspace widget. Frappe's own search bar and the awesome-bar history serve that.
