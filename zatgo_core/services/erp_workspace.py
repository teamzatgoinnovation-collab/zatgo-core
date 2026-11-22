"""The "ZatGo ERP" workspace: Accounts & Inventory, in one place.

Sidebar: Home, Dashboard, then the groups Transactions / Setup / Reports / Settings. Every link opens ERPNext's own
screen -- nothing is duplicated. The workspace belongs to the role ROLE ("ZG Accounts & Inventory",
setup/ensure_erp_perms.py also gives that role the document rights the links need) and to System Manager.

Single source: SECTIONS below. The synced Workspace file is generated from it
(`scripts/build_zatgo_erp_workspace.py` -- run it after editing SECTIONS); the Desk sidebar and the Apps-screen icon
are made on migrate by `sync_erp_desk()` (called from setup/ensure_core_desk.py). This is separate from the
"ZatGo" entry, which stays the platform-settings place (services/core_sidebar.py).
"""

from __future__ import annotations

NAME = "ZatGo ERP"
TITLE = "Accounts & Inventory"  # heading of the workspace page
ICON = "home"
MODULE = "ZatGo Core"
APP = "zatgo_core"
ROLE = "ZG Accounts & Inventory"
# The sidebar's "Dashboard" entry opens this Dashboard (shipped as zatgo_core_dashboard/zatgo_erp_dashboard/zatgo_erp_dashboard.json).
# It has its own name on purpose: Frappe picks the sidebar from the last part of the route, and "dashboard-view/Accounts"
# would switch to ERPNext's own "Accounts" sidebar and leave this one.
DASHBOARD = "ZatGo ERP Dashboard"
# ERPNext's standard charts and number cards, reused as they are: (name, width) / name.
DASHBOARD_CHARTS = (
    ("Profit and Loss", "Full"),
    ("Incoming Bills (Purchase Invoice)", "Half"),
    ("Outgoing Bills (Sales Invoice)", "Half"),
    ("Accounts Receivable Ageing", "Half"),
    ("Accounts Payable Ageing", "Half"),
    ("Bank Balance", "Full"),
    ("Warehouse wise Stock Value", "Full"),
    ("Delivery Trends", "Half"),
    ("Purchase Receipt Trends", "Half"),
)
DASHBOARD_CARDS = (
    "Total Outgoing Bills",
    "Total Incoming Bills",
    "Total Incoming Payment",
    "Total Outgoing Payment",
    "Total Active Items",
    "Total Stock Value",
)

# The role that owns the workspace (+ System Manager). ROLE is made by setup/ensure_roles.py.
ROLES = (ROLE, "System Manager")

# Bump when SECTIONS / ROLES / SHORTCUTS change: migrate re-imports a Workspace file only when this is newer than the
# site's copy (then run scripts/build_zatgo_erp_workspace.py).
WORKSPACE_MODIFIED = "2026-11-22 18:00:00.000000"


def _dt(label: str, link_to: str | None = None) -> dict:
    return {"label": label, "link_type": "DocType", "link_to": link_to or label}


def _rep(label: str, ref_doctype: str, script: bool = True) -> dict:
    return {"label": label, "link_type": "Report", "link_to": label, "ref_doctype": ref_doctype, "is_query_report": int(script)}


# (group label, sidebar icon, items)
SECTIONS = (
    (
        "Transactions",
        "sell",
        [
            _dt("Sales Invoice"),
            _dt("Purchase Invoice"),
            _dt("Sales Order"),
            _dt("Purchase Order"),
            _dt("Payment Entry"),
            _dt("Payment Reconciliation"),
        ],
    ),
    ("Setup", "stock", [_dt("Item"), _dt("Customer"), _dt("Supplier"), _dt("Warehouse")]),
    (
        "Reports",
        "file",
        [
            _rep("Profit and Loss Statement", "GL Entry"),
            _rep("Balance Sheet", "GL Entry"),
            _rep("Trial Balance", "GL Entry"),
            _rep("General Ledger", "GL Entry"),
            _rep("Stock Ledger", "Stock Ledger Entry"),
            _rep("Business Summary Report", "Sales Invoice"),
            _rep("Sales Register", "Sales Invoice"),
            _rep("Purchase Register", "Purchase Invoice"),
        ],
    ),
    (
        "Settings",
        "setting",
        [
            _dt("Accounts", "Accounts Settings"),
            _dt("Stock", "Stock Settings"),
            _dt("Buying", "Buying Settings"),
            _dt("Selling", "Selling Settings"),
            _dt("Print", "Print Settings"),
            _dt("System", "System Settings"),
        ],
    ),
)

# The most used documents: count + total tiles at the top of the Home page (the custom block below; same order as
# services/erp_summary.DOCS).
SHORTCUTS = ("Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order")

# The Custom HTML Block drawing those tiles, the top selling product and the top category. Its source is
# templates/erp_summary/block.{html,js,css}; ensure_block() copies it into the site on migrate.
BLOCK_NAME = "ZG ERP Summary"


# --------------------------------------------------------------------------- Workspace file (generated)


def workspace_json() -> dict:
    """The Workspace document as shipped in workspace/zatgo_erp/zatgo_erp.json (deterministic: no random ids)."""
    import json

    links, content = [], []
    content.append({"id": "zgerp_head", "type": "header", "data": {"text": f'<span class="h4"><b>{TITLE}</b></span>', "col": 12}})
    content.append({"id": "zgerp_blk", "type": "custom_block", "data": {"custom_block_name": BLOCK_NAME, "col": 12}})
    content.append({"id": "zgerp_sp", "type": "spacer", "data": {"col": 12}})
    for n, (label, _icon, items) in enumerate(SECTIONS):
        links.append({"hidden": 0, "is_query_report": 0, "label": label, "link_count": len(items), "onboard": 0, "type": "Card Break"})
        for it in items:
            row = {
                "dependencies": "",
                "hidden": 0,
                "is_query_report": it.get("is_query_report", 0),
                "label": it["label"],
                "link_count": 0,
                "link_to": it["link_to"],
                "link_type": it["link_type"],
                "onboard": 0,
                "type": "Link",
            }
            if it["link_type"] == "Report":
                row["report_ref_doctype"] = it["ref_doctype"]
            links.append(row)
        content.append({"id": f"zgerp_cd{n}", "type": "card", "data": {"card_name": label, "col": 3}})
    return {
        "app": APP,
        "charts": [],
        "content": json.dumps(content),
        "creation": "2026-11-22 00:00:00.000000",
        "custom_blocks": [{"doctype": "Workspace Custom Block", "custom_block_name": BLOCK_NAME, "label": BLOCK_NAME}],
        "docstatus": 0,
        "doctype": "Workspace",
        "for_user": "",
        "hide_custom": 0,
        "icon": ICON,
        "idx": 0,
        "is_hidden": 0,
        "label": NAME,
        "links": links,
        "modified": WORKSPACE_MODIFIED,
        "modified_by": "Administrator",
        "module": MODULE,
        "name": NAME,
        "number_cards": [],
        "owner": "Administrator",
        "parent_page": "",
        "public": 1,
        "quick_lists": [],
        "roles": [{"doctype": "Has Role", "role": r} for r in ROLES],
        "sequence_id": 2.0,
        "shortcuts": [],
        "title": NAME,
        "type": "Workspace",
    }


def dashboard_json() -> dict:
    """The Dashboard document as shipped in zatgo_core_dashboard/zatgo_erp_dashboard/zatgo_erp_dashboard.json (Frappe reads module dashboards from "<module>_dashboard")."""
    return {
        "cards": [{"doctype": "Number Card Link", "card": c} for c in DASHBOARD_CARDS],
        "charts": [{"doctype": "Dashboard Chart Link", "chart": c, "width": w} for c, w in DASHBOARD_CHARTS],
        "creation": "2026-11-22 00:00:00.000000",
        "dashboard_name": DASHBOARD,
        "docstatus": 0,
        "doctype": "Dashboard",
        "idx": 0,
        "is_default": 0,
        "is_standard": 1,
        "modified": WORKSPACE_MODIFIED,
        "modified_by": "Administrator",
        "module": MODULE,
        "name": DASHBOARD,
        "owner": "Administrator",
    }


# --------------------------------------------------------------------------- Desk sidebar + Apps-screen icon


def _sidebar_rows() -> list[dict]:
    """Home, Dashboard, then one Section Break per group with its links as children (Frappe nests one level only)."""
    top = {"collapsible": 1, "keep_closed": 0, "show_arrow": 0, "indent": 0, "child": 0, "type": "Link"}
    rows = [
        {**top, "label": "Home", "link_type": "Workspace", "link_to": NAME, "icon": "home"},
        {**top, "label": "Dashboard", "link_type": "Dashboard", "link_to": DASHBOARD, "icon": "dashboard"},
    ]
    for label, icon, items in SECTIONS:
        rows.append({"type": "Section Break", "label": label, "collapsible": 1, "keep_closed": 0, "indent": 0, "child": 0})
        for it in items:
            rows.append({**top, "label": it["label"], "link_type": it["link_type"], "link_to": it["link_to"], "icon": icon, "child": 1})
    return rows


def _row_key(r) -> tuple:
    get = r.get if isinstance(r, dict) else (lambda k, d=None: getattr(r, k, d))
    return (get("type"), get("label"), get("link_type") or "", get("link_to") or "", int(get("child") or 0))


def ensure_block() -> None:
    """Create or refresh the Custom HTML Block from templates/erp_summary (code and style follow the app on every migrate)."""
    import os

    import frappe

    folder = os.path.join(frappe.get_app_path(APP), "templates", "erp_summary")
    parts = {}
    for key, name in (("html", "block.html"), ("script", "block.js"), ("style", "block.css")):
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            parts[key] = f.read()
    if frappe.db.exists("Custom HTML Block", BLOCK_NAME):
        doc = frappe.get_doc("Custom HTML Block", BLOCK_NAME)
        if any(doc.get(k) != v for k, v in parts.items()):
            doc.update(parts)
            doc.save(ignore_permissions=True)
        return
    frappe.get_doc({"doctype": "Custom HTML Block", "name": BLOCK_NAME, "private": 0, **parts}).insert(ignore_permissions=True)


def sync_erp_desk() -> None:
    """Idempotent: Workspace (imported from its file if the migrate sync did not), Workspace Sidebar, Apps-screen icon.

    Rows are replaced only when they drift; a site's own Workspace edits are not touched here.
    """
    import os

    import frappe

    ensure_block()  # before the Workspace import: the workspace points at it
    if not frappe.db.exists("Workspace", NAME):
        from frappe.modules.import_file import import_file_by_path

        path = os.path.join(frappe.get_app_path(APP), "zatgo_core", "workspace", "zatgo_erp", "zatgo_erp.json")
        if os.path.exists(path):
            import_file_by_path(path, force=True)
    if not frappe.db.exists("Workspace", NAME):
        return  # nothing to point at

    rows = _sidebar_rows()
    if not frappe.db.exists("Workspace Sidebar", NAME):
        sb = frappe.get_doc(
            {"doctype": "Workspace Sidebar", "name": NAME, "title": NAME, "header_icon": ICON, "module": MODULE, "app": APP, "standard": 0, "items": rows}
        )
        sb.flags.ignore_links = True
        sb.insert(ignore_permissions=True)
    else:
        sb = frappe.get_doc("Workspace Sidebar", NAME)
        if [_row_key(r) for r in sb.items] != [_row_key(r) for r in rows]:
            sb.items = []
            for r in rows:
                sb.append("items", r)
            sb.flags.ignore_links = True
            sb.save(ignore_permissions=True)

    if not frappe.db.exists("Desktop Icon", NAME):
        icon = frappe.get_doc(
            {
                "doctype": "Desktop Icon", "label": NAME, "app": APP, "icon_type": "Link", "link_type": "Workspace Sidebar",
                "link_to": NAME, "icon": ICON, "standard": 0, "hidden": 0,
            }
        )
        icon.flags.ignore_links = True
        icon.insert(ignore_permissions=True)
