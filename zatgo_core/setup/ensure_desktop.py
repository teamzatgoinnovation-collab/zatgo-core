"""Ensure Frappe v16 Desktop Icon + Workspace Sidebar for ZatGo Core.

Desk home shows Desktop Icons that point at Workspace Sidebars — a Workspace
alone is not enough to appear on the module grid.
"""

from __future__ import annotations

import frappe

from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

SIDEBAR_NAME = "ZatGo Core"
ICON_LABEL = "ZatGo Core"
LEGACY_SIDEBAR = "Core Administration"

SIDEBAR_ITEMS = (
    ("Home", "Page", "zg-core"),
    ("Dashboard", "Page", "zg-core"),
    ("Applications", "Page", "zg-core"),
    ("System Settings", "DocType", "ZG System Settings"),
    ("Security", "DocType", "ZG Security Settings"),
    ("Integrations", "DocType", "ZG Integration Settings"),
    ("Registered Apps", "DocType", "ZG Registered Application"),
    ("Setting Sections", "DocType", "ZG Setting Section"),
    ("Client Apps", "DocType", "ZG Application Settings"),
    ("Feature Flags", "DocType", "ZG Feature Flag"),
    ("Audit Log", "DocType", "ZG Audit Log"),
    ("Config History", "DocType", "ZG Config History"),
)


def ensure_desktop() -> None:
    """Create/update Workspace Sidebar and Desktop Icon for ZatGo Core."""
    if not frappe.db.exists("DocType", "Workspace Sidebar"):
        logger.warning("Workspace Sidebar DocType missing; skip desktop ensure")
        return
    if not frappe.db.exists("DocType", "Desktop Icon"):
        logger.warning("Desktop Icon DocType missing; skip desktop ensure")
        return

    _ensure_sidebar()
    _ensure_desktop_icon()
    frappe.clear_cache()
    logger.info("Ensured Desktop Icon / Workspace Sidebar for ZatGo Core")


def _ensure_sidebar() -> None:
    items = [
        {
            "label": label,
            "type": "Link",
            "link_type": link_type,
            "link_to": link_to,
            "collapsible": 1,
        }
        for label, link_type, link_to in SIDEBAR_ITEMS
    ]

    # Prefer new name; migrate legacy sidebar title if present
    target = SIDEBAR_NAME
    if not frappe.db.exists("Workspace Sidebar", target):
        if frappe.db.exists("Workspace Sidebar", LEGACY_SIDEBAR):
            target = LEGACY_SIDEBAR

    if frappe.db.exists("Workspace Sidebar", target):
        doc = frappe.get_doc("Workspace Sidebar", target)
        doc.title = SIDEBAR_NAME
        doc.header_icon = "setting-gear"
        doc.module = "ZatGo Core"
        doc.items = []
        for row in items:
            doc.append("items", row)
        doc.save(ignore_permissions=True)
        # Rename sidebar document to ZatGo Core when possible
        if doc.name != SIDEBAR_NAME:
            try:
                frappe.rename_doc(
                    "Workspace Sidebar", doc.name, SIDEBAR_NAME, force=True
                )
            except Exception:
                logger.debug("Could not rename sidebar to ZatGo Core", exc_info=True)
        return

    doc = frappe.get_doc(
        {
            "doctype": "Workspace Sidebar",
            "name": SIDEBAR_NAME,
            "title": SIDEBAR_NAME,
            "header_icon": "setting-gear",
            "module": "ZatGo Core",
            "standard": 0,
            "items": items,
        }
    )
    doc.insert(ignore_permissions=True)


def _ensure_desktop_icon() -> None:
    link_to = SIDEBAR_NAME
    if not frappe.db.exists("Workspace Sidebar", SIDEBAR_NAME):
        if frappe.db.exists("Workspace Sidebar", LEGACY_SIDEBAR):
            link_to = LEGACY_SIDEBAR

    values = {
        "label": ICON_LABEL,
        "icon_type": "Link",
        "link_type": "Workspace Sidebar",
        "link_to": link_to,
        "icon": "setting-gear",
        "bg_color": "blue",
        "hidden": 0,
        "standard": 0,
        "app": "zatgo_core",
    }

    existing = frappe.db.exists("Desktop Icon", {"label": ICON_LABEL})
    if existing:
        doc = frappe.get_doc("Desktop Icon", existing)
        doc.update(values)
        doc.save(ignore_permissions=True)
        return

    if frappe.db.exists("Desktop Icon", ICON_LABEL):
        doc = frappe.get_doc("Desktop Icon", ICON_LABEL)
        doc.update(values)
        doc.save(ignore_permissions=True)
        return

    doc = frappe.get_doc({"doctype": "Desktop Icon", **values})
    doc.insert(ignore_permissions=True)
