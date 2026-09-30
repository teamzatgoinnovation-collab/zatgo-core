"""VanSaleX (van sales mobile app) settings manifest for the configuration center."""

from __future__ import annotations

MANIFEST = {
    "app_key": "vansalex",
    "title": "VanSaleX",
    "version": "0.1.0",
    "icon": "sell",
    "category": "Sales",
    "menu_order": 15,
    "enabled": 1,
    "visible": 1,
    "roles": "System Manager,ZG Application Admin,ZG Company Admin,VanSale Admin",
    "depends_on": "",
    "description": "Van sales mobile app — cash/credit, warehouses, per-driver profiles",
    "settings_route": "/app/vansalex",
    "sections": [
        {
            "section_key": "general",
            "label": "VanSaleX Settings",
            "icon": "setting",
            "sort_order": 10,
            "link_doctype": "VanSaleX Settings",
            "component": "",
        },
        {
            "section_key": "profiles",
            "label": "Driver Profiles",
            "icon": "users",
            "sort_order": 20,
            "link_doctype": "ZG Van Sale Profile",
            "component": "",
        },
        {
            "section_key": "company",
            "label": "Company Defaults",
            "icon": "organization",
            "sort_order": 30,
            "link_doctype": "ZG Company Settings",
            "component": "",
        },
        {
            "section_key": "payments",
            "label": "Payment Methods",
            "icon": "money",
            "sort_order": 40,
            "link_doctype": "ZG Payment Settings",
            "component": "",
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
