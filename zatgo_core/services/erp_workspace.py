"""The "ZatGo ERP" workspace: Accounts & Inventory, in one place.

The **Workspace record is the source of truth**, like every other ZatGo app: an administrator adds a DocType / Page / Report
by editing the workspace in Desk (a link in a card), and the sidebar follows at once (services/app_sidebar.py builds it from
the Workspace and re-syncs when it is saved, hooks.py doc_events). Every link opens ERPNext's own screen.

What this module holds are the **defaults** a site starts with: SECTIONS (cards and their links), the roles, the summary block
(templates/erp_summary), the Dashboard and its Number Cards. `scripts/build_zatgo_erp_workspace.py` writes them to the
synced files. A later release that adds a default item reaches existing sites through `ensure_default_items()`: added once,
never removed, never overwriting what the site changed (an item an administrator deleted stays deleted).

The role ROLE ("ZG Accounts & Inventory", setup/ensure_erp_perms.py gives it the document rights the links need) and ERPNext's
working roles see the workspace. `sync_erp_desk()` (called from setup/ensure_core_desk.py) runs on install and every migrate.
This is separate from the "ZatGo" entry, which stays the platform-settings place (services/core_sidebar.py).
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
# Our own Number Cards (zatgo_core/zatgo_core/number_card/): count and Grand Total of the submitted documents.
# (label, DocType, function, field summed)
NUMBER_CARDS = (
    ("ZG Sales Invoices", "Sales Invoice", "Count", None),
    ("ZG Sales Invoice Total", "Sales Invoice", "Sum", "base_grand_total"),
    ("ZG Purchase Invoices", "Purchase Invoice", "Count", None),
    ("ZG Purchase Invoice Total", "Purchase Invoice", "Sum", "base_grand_total"),
    ("ZG Sales Orders", "Sales Order", "Count", None),
    ("ZG Sales Order Total", "Sales Order", "Sum", "base_grand_total"),
    ("ZG Purchase Orders", "Purchase Order", "Count", None),
    ("ZG Purchase Order Total", "Purchase Order", "Sum", "base_grand_total"),
)
DASHBOARD_CARDS = tuple(c[0] for c in NUMBER_CARDS) + (
    "Total Outgoing Bills",
    "Total Incoming Bills",
    "Total Incoming Payment",
    "Total Outgoing Payment",
    "Total Active Items",
    "Total Stock Value",
)

# Who sees the workspace and its Apps-screen icon: the role that owns it (ROLE, made by setup/ensure_roles.py), System
# Manager and ERPNext's own working roles, so existing staff need nothing extra. What each person can open inside it is
# still decided by their own document rights (Frappe hides a link they may not use); ROLE is the one that grants those rights
# (setup/ensure_erp_perms.py). ERPNext standard roles only: they exist when the Workspace file is imported (ZG roles do not yet
# on a fresh install).
STANDARD_ROLES = (
    "System Manager",
    "Accounts User",
    "Accounts Manager",
    "Sales User",
    "Sales Manager",
    "Purchase User",
    "Purchase Manager",
    "Stock User",
    "Stock Manager",
    "Manufacturing User",
    "Manufacturing Manager",
)
ROLES = (ROLE,) + STANDARD_ROLES

# migrate re-imports a synced file only when its `modified` is newer than the site's copy, which OVERWRITES the site's copy.
# So WORKSPACE_MODIFIED stays as it is (the workspace is the site's to edit; new default items go through
# ensure_default_items()). DASHBOARD_MODIFIED / NUMBER_CARDS_MODIFIED are bumped when the dashboard or the cards change (code-owned).
WORKSPACE_MODIFIED = "2026-11-22 21:00:00.000000"
DASHBOARD_MODIFIED = "2026-11-23 22:00:00.000000"
NUMBER_CARDS_MODIFIED = "2026-11-23 22:00:00.000000"


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


# The "Dashboard" tile on the page and entry in the sidebar: a Workspace shortcut of type Dashboard. It must be in the page content
# too: Frappe's editor drops shortcuts that no content block shows.
DASHBOARD_SHORTCUT_BLOCK = {"id": "zgerp_db", "type": "shortcut", "data": {"shortcut_name": "Dashboard", "col": 3}}
DASHBOARD_SHORTCUT_ROW = {
    "doctype": "Workspace Shortcut", "label": "Dashboard", "link_to": DASHBOARD, "type": "Dashboard",
    "color": "Grey", "format": "{}", "stats_filter": "[]", "doc_view": "List",
}


def app_dict() -> dict:
    """ZatGo ERP described like a catalog app (services/app_sidebar.py builds its sidebar from the Workspace).

    Not in the app catalog on purpose: a catalog app's rail icon is hidden and listed in the ZatGo folder; ZatGo ERP keeps its own icon."""
    return {
        "key": "zatgo_erp",
        "label": NAME,
        "icon": ICON,
        "workspaces": (NAME,),
        "settings": (),
        "overview_label": "Home",
        "group_icons": {label: icon for label, icon, _items in SECTIONS},
    }


# --------------------------------------------------------------------------- Workspace file (generated)


def workspace_json() -> dict:
    """The Workspace document as shipped in workspace/zatgo_erp/zatgo_erp.json (deterministic: no random ids)."""
    import json

    links, content = [], []
    content.append({"id": "zgerp_head", "type": "header", "data": {"text": f'<span class="h4"><b>{TITLE}</b></span>', "col": 12}})
    content.append({"id": "zgerp_blk", "type": "custom_block", "data": {"custom_block_name": BLOCK_NAME, "col": 12}})
    content.append(DASHBOARD_SHORTCUT_BLOCK)
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
        "shortcuts": [dict(DASHBOARD_SHORTCUT_ROW)],
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
        "modified": DASHBOARD_MODIFIED,
        "modified_by": "Administrator",
        "module": MODULE,
        "name": DASHBOARD,
        "owner": "Administrator",
    }


def number_card_json(label: str, doctype: str, function: str, field: str | None) -> dict:
    """A standard Number Card (zatgo_core/zatgo_core/number_card/<name>/<name>.json): submitted documents of `doctype`."""
    import json

    return {
        "aggregate_function_based_on": field or "",
        "creation": "2026-11-23 00:00:00.000000",
        "docstatus": 0,
        "doctype": "Number Card",
        "document_type": doctype,
        "dynamic_filters_json": "[]",
        "filters_json": json.dumps([[doctype, "docstatus", "=", "1"]]),
        "function": function,
        "idx": 0,
        "is_public": 1,
        "is_standard": 1,
        "label": label,
        "modified": NUMBER_CARDS_MODIFIED,
        "modified_by": "Administrator",
        "module": MODULE,
        "name": label,
        "owner": "Administrator",
        "show_percentage_stats": 1,
        "stats_time_interval": "Monthly",
        "type": "Document Type",
    }


# --------------------------------------------------------------------------- Desk sidebar + Apps-screen icon


def _add_link(ws, card: str, item: dict) -> bool:
    """Add [item] at the end of the Workspace card [card]. False when the card is not there (an administrator removed it)."""
    rows = list(ws.links)
    start = next((i for i, r in enumerate(rows) if r.type == "Card Break" and r.label == card), None)
    if start is None:
        return False
    end = next((i for i in range(start + 1, len(rows)) if rows[i].type == "Card Break"), len(rows))
    new = ws.append(
        "links",
        {
            "type": "Link", "label": item["label"], "link_type": item["link_type"], "link_to": item["link_to"],
            "is_query_report": item.get("is_query_report", 0), "hidden": 0, "onboard": 0, "dependencies": "",
            "report_ref_doctype": item.get("ref_doctype") if item["link_type"] == "Report" else None,
        },
    )
    ws.links.remove(new)
    ws.links.insert(end, new)
    for i, r in enumerate(ws.links, 1):
        r.idx = i
    rows[start].link_count = (rows[start].link_count or 0) + 1
    return True


def ensure_default_items() -> None:
    """Add the defaults this release ships that the site's Workspace does not have yet -- once each.

    The Workspace belongs to the site (administrators edit it in Desk), so this never removes or reorders anything: an item
    is added when it is missing, and a marker records it, so an item deleted later is not brought back. Shipped files
    already carry every default, so on a fresh site this only sets the markers."""
    import json

    import frappe

    if not frappe.db.exists("Workspace", NAME):
        return
    ws = frappe.get_doc("Workspace", NAME)
    changed = False
    for card, _icon, items in SECTIONS:
        for it in items:
            marker = f"zg_erp_ws_{frappe.scrub(it['link_type'])}_{frappe.scrub(it['link_to'])}"
            if frappe.db.get_global(marker):
                continue
            if not any(r.type == "Link" and r.link_type == it["link_type"] and r.link_to == it["link_to"] for r in ws.links):
                changed = _add_link(ws, card, it) or changed
            frappe.db.set_global(marker, 1)
    marker = "zg_erp_ws_shortcut_dashboard"
    if not frappe.db.get_global(marker):
        if not any(s.type == "Dashboard" and s.link_to == DASHBOARD for s in ws.shortcuts):
            ws.append("shortcuts", dict(DASHBOARD_SHORTCUT_ROW))
            blocks = json.loads(ws.content or "[]")
            if not any(b.get("type") == "shortcut" and b["data"].get("shortcut_name") == "Dashboard" for b in blocks):
                at = next((i + 1 for i, b in enumerate(blocks) if b.get("type") == "custom_block"), 1)
                blocks.insert(at, DASHBOARD_SHORTCUT_BLOCK)
                ws.content = json.dumps(blocks)
            changed = True
        frappe.db.set_global(marker, 1)
    if changed:
        ws.flags.ignore_links = True
        ws.save(ignore_permissions=True)


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
    """Idempotent: Workspace (imported from its file if the migrate sync did not), its missing default items, the Workspace
    Sidebar built from it, and the Apps-screen icon. A site's own Workspace edits are kept."""
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

    ensure_default_items()
    from zatgo_core.services import app_sidebar

    app_sidebar.sync_for_workspace(NAME)  # the sidebar is built from the Workspace (Home, Dashboard, one group per card)

    if not frappe.db.exists("Desktop Icon", NAME):
        icon = frappe.get_doc(
            {
                "doctype": "Desktop Icon", "label": NAME, "app": APP, "icon_type": "Link", "link_type": "Workspace Sidebar",
                "link_to": NAME, "icon": ICON, "standard": 0, "hidden": 0, "roles": [{"role": r} for r in ROLES],
            }
        )
        icon.flags.ignore_links = True
        icon.insert(ignore_permissions=True)
    else:
        # An icon that already exists (made by Frappe from an older workspace of this name, or by an earlier version) is
        # brought to what this app ships: picture, target, app, visible, top level -- and the Workspace's roles.
        icon = frappe.get_doc("Desktop Icon", NAME)
        wanted = {
            "icon_type": "Link", "link_type": "Workspace Sidebar", "link_to": NAME, "icon": ICON, "app": APP, "hidden": 0,
            "parent_icon": None,
        }
        changed = False
        for key, value in wanted.items():
            if (icon.get(key) or None) != (value or None) and (value or icon.get(key)):
                icon.set(key, value)
                changed = True
        if {r.role for r in icon.get("roles", [])} != set(ROLES):
            icon.set("roles", [{"role": r} for r in ROLES])
            changed = True
        if changed:
            icon.flags.ignore_links = True
            icon.save(ignore_permissions=True)
    frappe.cache.hdel("desktop_icons", frappe.session.user)  # other users' lists are rebuilt by clear-cache / their next boot
