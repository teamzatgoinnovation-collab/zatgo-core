"""Delivery settings manifest for the configuration center."""

from __future__ import annotations

MANIFEST = {
    "app_key": "delivery",
    "title": "Delivery",
    "version": "0.1.0",
    "icon": "shipment",
    "category": "Operations",
    "menu_order": 20,
    "enabled": 1,
    "visible": 1,
    "roles": "System Manager,ZG Application Admin,ZG Company Admin,ZG Branch Admin",
    "depends_on": "",
    "description": "Delivery zones, drivers, and notifications",
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
            "section_key": "zones",
            "label": "Zones",
            "icon": "map",
            "sort_order": 20,
            "component": "pending",
            "description": "Delivery zones — configure per branch",
        },
        {
            "section_key": "drivers",
            "label": "Drivers",
            "icon": "user",
            "sort_order": 30,
            "link_doctype": "ZG Delivery Boy",
            "component": "",
        },
        {
            "section_key": "stops",
            "label": "Delivery Stops",
            "icon": "list",
            "sort_order": 40,
            "link_doctype": "ZG Delivery Stop",
            "component": "",
        },
        {
            "section_key": "notifications",
            "label": "Notifications",
            "icon": "notification",
            "sort_order": 50,
            "link_doctype": "ZG Notification Settings",
            "component": "",
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
