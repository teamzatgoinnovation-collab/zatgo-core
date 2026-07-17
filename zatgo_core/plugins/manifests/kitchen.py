"""Kitchen settings manifest for the configuration center."""

from __future__ import annotations

MANIFEST = {
    "app_key": "kitchen",
    "title": "Kitchen",
    "version": "0.1.0",
    "icon": "cuisine",
    "category": "Operations",
    "menu_order": 30,
    "enabled": 1,
    "visible": 1,
    "roles": "System Manager,ZG Application Admin,ZG Company Admin,ZG Branch Admin",
    "depends_on": "zatgo_pos",
    "description": "Kitchen display and station configuration",
    "settings_route": "zg-core",
    "sections": [
        {
            "section_key": "general",
            "label": "General",
            "icon": "setting",
            "sort_order": 10,
            "link_doctype": "ZG Branch Settings",
            "component": "",
        },
        {
            "section_key": "stations",
            "label": "Stations",
            "icon": "organization",
            "sort_order": 20,
            "link_doctype": "ZG KDS Ticket",
            "component": "",
            "description": "KDS tickets / station board",
        },
        {
            "section_key": "printers",
            "label": "Printers",
            "icon": "printer",
            "sort_order": 30,
            "link_doctype": "ZG Printer Settings",
            "component": "",
        },
        {
            "section_key": "display",
            "label": "Display",
            "icon": "desktop",
            "sort_order": 40,
            "component": "pending",
        },
        {
            "section_key": "advanced",
            "label": "Advanced",
            "icon": "setting-gear",
            "sort_order": 90,
            "component": "pending",
        },
        {
            "section_key": "about",
            "label": "About",
            "icon": "info",
            "sort_order": 200,
            "component": "about",
        },
    ],
}
