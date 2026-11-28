"""One Desk workspace per ZatGo module (Phase 6): ZatGo Sales, Purchase, Stock, Accounting, Production, Quality,
Service, HR and Reports, next to ZatGo ERP (the home: Accounts & Inventory, services/erp_workspace.py) and the
ZatGo entry (General Settings, services/core_sidebar.py).

Each workspace is an ordinary Frappe Workspace with its own Workspace Sidebar (built by services/app_sidebar.py from
the workspace, like every ZatGo app) and an Apps-screen icon. Every link opens ERPNext's own screen: nothing here
duplicates ERPNext. A link is added only when its DocType / Report exists on the site (HR needs the hrms app, for
example), so one definition serves every site.

Who sees what:
- **module enabled** (Module Settings) **and "Show in navigation"** ticked: the workspace, its sidebar and its icon
  are shown; otherwise they are hidden. Hiding never deletes anything, and a hidden module's functions still work
  when it is enabled (visibility is not security).
- **roles**: the workspace and icon list the ERPNext roles of their area (only roles that exist on the site), plus
  System Manager. Frappe shows them only to those users.
- **document rights**: inside, Frappe hides every link the user may not open.

The workspace is created once (`ensure`) and then belongs to the site: an administrator may edit it in Desk, and the
sidebar follows (hooks.py `Workspace.on_update`). Visibility is re-applied on every migrate and whenever Module
Settings is saved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import frappe

APP = "zatgo_core"
MODULE = "ZatGo Core"


@dataclass(frozen=True)
class Spec:
    key: str  # app_sidebar key
    module: str  # licensing-registry module id
    name: str  # Workspace / Sidebar / Desktop Icon name
    icon: str
    roles: tuple[str, ...]
    sections: tuple[tuple[str, str, tuple[tuple[str, str, str], ...]], ...]  # (card, icon, ((kind, label, target)...))
    quick: tuple[tuple[str, str, str], ...] = ()  # (label, DocType, doc_view) shortcuts
    cards: tuple[str, ...] = field(default=())  # Number Card names


def _d(label: str, doctype: str | None = None) -> tuple[str, str, str]:
    return ("DocType", label, doctype or label)


def _r(label: str, report: str | None = None) -> tuple[str, str, str]:
    return ("Report", label, report or label)


def _p(label: str, page: str) -> tuple[str, str, str]:
    return ("Page", label, page)


SPECS: tuple[Spec, ...] = (
    Spec("zatgo_sales", "sales", "ZatGo Sales", "sell", ("Sales User", "Sales Manager", "Accounts User"), (
        ("Transactions", "file", (_d("Quotation"), _d("Sales Order"), _d("Delivery Note"), _d("Sales Invoice"))),
        ("Customers", "customer", (_d("Customer"), _d("Customer Group"), _d("Contact"), _d("Address"))),
        ("Items and Prices", "stock", (_d("Item"), _d("Price List"), _d("Item Price"), _d("Pricing Rule"))),
        ("Reports", "table", (_r("Sales Analytics"), _r("Sales Register"), _r("Sales Order Analysis"),
                              _r("Item-wise Sales History"), _r("Gross Profit"), _r("Customer Ledger Summary"))),
    ), quick=(("New Sales Invoice", "Sales Invoice", "New"), ("New Sales Order", "Sales Order", "New"),
              ("New Quotation", "Quotation", "New"), ("Customers", "Customer", "List")),
        cards=("ZatGo Sales Invoices", "ZatGo Sales Invoice Total", "ZatGo Sales Orders", "ZatGo Sales Order Total")),
    Spec("zatgo_purchase", "procurement", "ZatGo Purchase", "buying", ("Purchase User", "Purchase Manager", "Accounts User"), (
        ("Transactions", "file", (_d("Material Request"), _d("Request for Quotation"), _d("Supplier Quotation"),
                                  _d("Purchase Order"), _d("Purchase Receipt"), _d("Purchase Invoice"))),
        ("Suppliers", "supplier", (_d("Supplier"), _d("Supplier Group"), _d("Contact"), _d("Address"))),
        ("Reports", "table", (_r("Purchase Analytics"), _r("Purchase Register"), _r("Purchase Order Analysis"),
                              _r("Item-wise Purchase History"), _r("Supplier Ledger Summary"))),
    ), quick=(("New Purchase Invoice", "Purchase Invoice", "New"), ("New Purchase Order", "Purchase Order", "New"),
              ("New Material Request", "Material Request", "New"), ("Suppliers", "Supplier", "List")),
        cards=("ZatGo Purchase Invoices", "ZatGo Purchase Invoice Total", "ZatGo Purchase Orders", "ZatGo Purchase Order Total")),
    Spec("zatgo_stock", "inventory", "ZatGo Stock", "stock", ("Stock User", "Stock Manager"), (
        ("Transactions", "file", (_d("Stock Entry"), _d("Stock Reconciliation"), _d("Delivery Note"), _d("Purchase Receipt"),
                                  _d("Material Request"))),
        ("Items and Warehouses", "stock", (_d("Item"), _d("Item Group"), _d("Warehouse"), _d("UOM"), _d("Batch"),
                                           _d("Serial No"))),
        ("Reports", "table", (_r("Stock Balance"), _r("Stock Ledger"), _r("Stock Projected Qty"), _r("Stock Ageing"),
                              _r("Item Shortage Report"))),
    ), quick=(("New Stock Entry", "Stock Entry", "New"), ("Stock Reconciliation", "Stock Reconciliation", "New"),
              ("Items", "Item", "List"), ("Warehouses", "Warehouse", "Tree")),
        cards=("Total Stock Value", "Total Active Items")),
    Spec("zatgo_accounting", "accounting", "ZatGo Accounting", "accounting", ("Accounts User", "Accounts Manager", "Auditor"), (
        ("Transactions", "file", (_d("Payment Entry"), _d("Journal Entry"), _d("Sales Invoice"), _d("Purchase Invoice"),
                                  _d("Payment Reconciliation"))),
        ("Setup", "setting", (_d("Chart of Accounts", "Account"), _d("Cost Center"), _d("Mode of Payment"),
                              _d("Sales Taxes and Charges Template"), _d("Fiscal Year"))),
        ("Reports", "table", (_r("General Ledger"), _r("Trial Balance"), _r("Profit and Loss Statement"), _r("Balance Sheet"),
                              _r("Cash Flow"), _r("Accounts Receivable"), _r("Accounts Payable"))),
    ), quick=(("New Payment Entry", "Payment Entry", "New"), ("New Journal Entry", "Journal Entry", "New"),
              ("Chart of Accounts", "Account", "Tree")),
        cards=("Total Outgoing Bills", "Total Incoming Bills", "Total Incoming Payment", "Total Outgoing Payment")),
    Spec("zatgo_production", "production", "ZatGo Production", "organization", ("Manufacturing User", "Manufacturing Manager"), (
        ("Production", "file", (_d("Work Order"), _d("Job Card"), _d("Production Plan"), _d("BOM"))),
        ("Setup", "setting", (_d("Workstation"), _d("Operation"), _d("Routing"))),
        ("Reports", "table", (_r("Production Planning Report"), _r("Work Order Summary"), _r("BOM Stock Report"))),
    ), quick=(("New Work Order", "Work Order", "New"), ("BOM", "BOM", "List"))),
    Spec("zatgo_quality", "quality", "ZatGo Quality", "quality", ("Quality Manager", "Manufacturing User", "Stock User"), (
        ("Inspection", "file", (_d("Quality Inspection"), _d("Quality Inspection Template"), _d("Non Conformance"))),
        ("Management", "setting", (_d("Quality Goal"), _d("Quality Procedure"), _d("Quality Review"), _d("Quality Action"),
                                   _d("Quality Meeting"))),
        ("Reports", "table", (_r("Quality Inspection Summary"),)),
    ), quick=(("New Quality Inspection", "Quality Inspection", "New"),)),
    Spec("zatgo_service", "service", "ZatGo Service", "support", ("Support Team", "Maintenance User", "Maintenance Manager"), (
        ("Service", "file", (_d("Issue"), _d("Service Ticket"), _d("Warranty Claim"), _d("Maintenance Visit"),
                             _d("Maintenance Schedule"))),
        ("Setup", "setting", (_d("Issue Type"), _d("Service Level Agreement"))),
        ("Reports", "table", (_r("Issue Analytics"), _r("Issue Summary"))),
    ), quick=(("New Issue", "Issue", "New"), ("Service Tickets", "Service Ticket", "List"))),
    Spec("zatgo_hr", "hr_payroll", "ZatGo HR", "hr", ("HR User", "HR Manager"), (
        ("Employees", "users", (_d("Employee"), _d("Department"), _d("Designation"), _d("Branch"), _d("Holiday List"))),
        ("Attendance and Leave", "calendar", (_d("Attendance"), _d("Leave Application"), _d("Leave Allocation"))),
        ("Payroll", "accounting", (_d("Salary Structure"), _d("Salary Slip"), _d("Payroll Entry"))),
    ), quick=(("Employees", "Employee", "List"),)),
    # Phase 7: the settings landing page. ERPNext's own settings come first; ZatGo's only where ZatGo adds something.
    Spec("zatgo_settings", "foundation", "ZatGo Settings", "setting", ("ZatGo Application Admin", "ZatGo Company Admin"), (
        ("General", "setting", (_d("System Settings"), _d("Global Defaults"), _d("Company"), _d("Currency"),
                                _d("ZatGo System Settings"))),
        ("Modules", "grid", (_d("Modules", "Module Settings"), _p("ZatGo Apps", "zg-app-hub"), _p("Licence", "zg-licence"))),
        ("Sales", "sell", (_d("Selling Settings"), _d("Sales Invoice Naming Settings"), _d("VanSaleX Settings"),
                           _d("ZatGo POS Settings"), _d("Price List"))),
        ("Purchase", "buying", (_d("Buying Settings"), _d("Supplier Group"))),
        ("Inventory", "stock", (_d("Stock Settings"), _d("Warehouse"), _d("UOM"), _d("Item Group"))),
        ("Accounting", "accounting", (_d("Accounts Settings"), _d("Company Settings"), _d("Mode of Payment"),
                                      _d("Fiscal Year"), _d("Currency Exchange Settings"))),
        ("Print", "printer", (_d("Print Settings"), _d("Print Format"), _d("Letter Head"),
                              _d("Print Format per User (A4 / 80mm)", "Sales Invoice Naming Settings"))),
        ("Tax and Compliance", "tax", (_d("Sales Taxes and Charges Template"), _d("Purchase Taxes and Charges Template"),
                                       _d("Item Tax Template"), _d("Tax Category"))),
        ("Users and Access", "users", (_d("User"), _d("Role"), _p("Role Permissions", "permission-manager"),
                                       _d("User Permission"), _d("Role Profile"), _d("Van Sale Profile"))),
        ("Advanced", "tool", (_d("Integration Settings"), _d("ZatGo Notification Settings"), _d("Application Settings"),
                              _d("Duplicate Prevention Settings"), _d("Audit Log"), _d("Error Log"),
                              _d("Scheduled Job Log"))),
    ), quick=(("Modules", "Module Settings", "List"), ("System Settings", "System Settings", "List"),
              ("Users", "User", "List"))),
    Spec("zatgo_reports", "reports", "ZatGo Reports", "table", ("Accounts Manager", "Sales Manager", "Purchase Manager",
                                                                "Stock Manager"), (
        ("ZatGo", "star", (_r("Business Summary Report"), _r("Payment Method Summary"))),
        ("Financial", "accounting", (_r("Profit and Loss Statement"), _r("Balance Sheet"), _r("Trial Balance"),
                                     _r("Accounts Receivable"), _r("Accounts Payable"))),
        ("Sales and Purchase", "sell", (_r("Sales Analytics"), _r("Purchase Analytics"), _r("Gross Profit"))),
        ("Stock", "stock", (_r("Stock Balance"), _r("Stock Ledger"), _r("Stock Ageing"))),
    )),
)


def specs() -> tuple[Spec, ...]:
    return SPECS


def get(name_or_key: str) -> Spec | None:
    return next((s for s in SPECS if name_or_key in (s.name, s.key, s.module)), None)


def name_for_module(module_id: str) -> str | None:
    spec = get(module_id)
    return spec.name if spec and spec.module == module_id else None


def app_dict(spec: Spec) -> dict:
    """The spec described like a catalog app, for services/app_sidebar.py."""
    return {"key": spec.key, "label": spec.name, "icon": spec.icon, "workspaces": (spec.name,), "settings": (),
            "overview_label": "Home", "group_icons": {label: icon for label, icon, _items in spec.sections}}


def _roles(spec: Spec) -> list[str]:
    return [r for r in (*spec.roles, "System Manager") if frappe.db.exists("Role", r)]


def _links(spec: Spec) -> list[tuple[str, str, list[dict]]]:
    """The spec's cards with only the links that exist on this site (empty cards left out)."""
    cards = []
    for label, icon, items in spec.sections:
        rows = []
        for kind, item_label, target in items:
            if kind == "DocType" and frappe.db.exists("DocType", target):
                rows.append({"link_type": "DocType", "label": item_label, "link_to": target})
            elif kind == "Page" and frappe.db.exists("Page", target):
                rows.append({"link_type": "Page", "label": item_label, "link_to": target})
            elif kind == "Report" and frappe.db.exists("Report", target):
                ref = frappe.db.get_value("Report", target, ["ref_doctype", "report_type"], as_dict=True)
                rows.append({"link_type": "Report", "label": item_label, "link_to": target, "report_ref_doctype": ref.ref_doctype,
                             "is_query_report": 1 if ref.report_type in ("Script Report", "Query Report") else 0})
        if rows:
            cards.append((label, icon, rows))
    return cards


def workspace_doc(spec: Spec) -> dict:
    """The Workspace as it is first created on a site (links, shortcuts and cards that exist there)."""
    import json

    cards = _links(spec)
    quick = [(label, dt, view) for label, dt, view in spec.quick if frappe.db.exists("DocType", dt)]
    number_cards = [c for c in spec.cards if frappe.db.exists("Number Card", c)]
    content = [{"id": f"{spec.key}_h", "type": "header", "data": {"text": f'<span class="h4"><b>{spec.name}</b></span>', "col": 12}}]
    content += [{"id": f"{spec.key}_n{i}", "type": "number_card", "data": {"number_card_name": c, "col": 3}}
                for i, c in enumerate(number_cards)]
    content += [{"id": f"{spec.key}_q{i}", "type": "shortcut", "data": {"shortcut_name": label, "col": 3}}
                for i, (label, _dt, _v) in enumerate(quick)]
    content += [{"id": f"{spec.key}_sp", "type": "spacer", "data": {"col": 12}}]
    content += [{"id": f"{spec.key}_c{i}", "type": "card", "data": {"card_name": label, "col": 4}}
                for i, (label, _icon, _rows) in enumerate(cards)]
    links = []
    for label, _icon, rows in cards:
        links.append({"type": "Card Break", "label": label, "link_count": len(rows), "hidden": 0, "onboard": 0})
        links += [{"type": "Link", "hidden": 0, "onboard": 0, "link_count": 0, "dependencies": "", **row} for row in rows]
    return {
        "doctype": "Workspace", "name": spec.name, "label": spec.name, "title": spec.name, "icon": spec.icon,
        # No module/app: Frappe's migrate deletes public workspaces made in code that carry them (orphans).
        "public": 1, "is_hidden": 0, "content": json.dumps(content), "links": links,
        "shortcuts": [{"label": label, "type": "DocType", "link_to": dt, "doc_view": view} for label, dt, view in quick],
        "number_cards": [{"number_card_name": c, "label": c} for c in number_cards],
        "roles": [{"role": r} for r in _roles(spec)],
    }


def _visible(spec: Spec) -> bool:
    from zatgo_core.services import module_settings

    return module_settings.is_enabled(spec.module) and module_settings.shows_in_navigation(spec.module) \
        and module_settings.is_installed(spec.module)


def _ensure_icon(spec: Spec, hidden: int) -> None:
    if not frappe.db.exists("Desktop Icon", spec.name):
        icon = frappe.get_doc({
            "doctype": "Desktop Icon", "label": spec.name, "app": APP, "icon_type": "Link", "link_type": "Workspace Sidebar",
            "link_to": spec.name, "icon": spec.icon, "standard": 0, "hidden": hidden, "roles": [{"role": r} for r in _roles(spec)],
        })
        icon.flags.ignore_links = True
        icon.insert(ignore_permissions=True)
    elif frappe.db.get_value("Desktop Icon", spec.name, "hidden") != hidden:
        frappe.db.set_value("Desktop Icon", spec.name, "hidden", hidden, update_modified=False)


def ensure() -> list[str]:
    """Create the missing module workspaces (once: later they are the site's), then apply visibility. Returns the names
    created. A module whose app is not installed gets no workspace."""
    from zatgo_core.licensing import registry
    from zatgo_core.services import module_settings

    created = []
    for spec in SPECS:
        if registry.get_module(spec.module) is None or not module_settings.is_installed(spec.module):
            continue
        if not frappe.db.exists("Workspace", spec.name):
            ws = frappe.get_doc(workspace_doc(spec))
            ws.flags.ignore_links = True
            ws.insert(ignore_permissions=True)
            created.append(spec.name)
    sync_visibility()
    return created


def sync_visibility() -> None:
    """Show or hide each module workspace, its sidebar and its icon from Module Settings (enabled + Show in navigation)."""
    from zatgo_core.services import app_sidebar

    for spec in SPECS:
        if not frappe.db.exists("Workspace", spec.name):
            continue
        visible = _visible(spec)
        if frappe.db.get_value("Workspace", spec.name, "is_hidden") != (0 if visible else 1):
            frappe.db.set_value("Workspace", spec.name, "is_hidden", 0 if visible else 1, update_modified=False)
        app_sidebar.sync_module_sidebar(app_dict(spec), visible)
        _ensure_icon(spec, 0 if visible else 1)
