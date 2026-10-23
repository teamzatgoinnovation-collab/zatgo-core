"""Core entries of the App Settings Hub: zatgo_core's own settings DocTypes,
the Desk-appearance switches (SaaS theme, language switcher, VanSaleX web) and
Industries. Module sub-apps (Chat AI, Tracker, ...) ship their own
`<module>/app_manifest.py`; see services/app_catalog.py."""

from __future__ import annotations

APPS = (
    {
        "key": "core_settings",
        "label": "Core settings",
        "group": "core",
        "icon": "setting",
        "description": "System, company, branch, payment, security and numbering settings.",
        "settings": (
            ("ZG System Settings", "System Settings"),
            ("ZG Application Settings", "Application Settings"),
            ("ZG Integration Settings", "Integrations"),
            ("ZG Storage Settings", "Storage"),
            ("ZG Security Settings", "Security"),
            ("ZG Payment Settings", "Payments"),
            ("ZG Printer Settings", "Printers"),
            ("ZG Notification Settings", "Notifications"),
            ("ZG Sync Settings", "Sync"),
            ("ZG Number Series Settings", "Number Series"),
            ("ZG Sales Invoice Naming Settings", "Sales Invoice Naming"),
        ),
    },
    {
        "key": "vansalex",
        "label": "ZatGo VanSaleX",
        "group": "app",
        "icon": "truck",
        "description": "Mobile van sales: warehouses, Cash/Credit rules, modules and features per user.",
        # On everywhere it was before it had a switch (a site with no stored value counts as on).
        "switch_field": "enable_vansalex",
        "default_on": True,
        "workspaces": ("ZatGo VanSaleX", "VanSaleX"),
        "settings": (("VanSaleX Settings", "VanSaleX Settings"),),
        # Off: the VanSaleX app's own API answers 404. The shared accounting / warehouse endpoints other
        # clients use are not VanSaleX's and stay up.
        "api_prefixes": ("zatgo_core.api.v1.vansalex.",),
    },
    {
        "key": "saas_theme",
        "label": "ZatGo Desk Theme",
        "group": "ui",
        "icon": "color",
        "description": "Modern Desk theme and login page.",
        "switch_field": "enable_saas_theme",
    },
    {
        "key": "language_switcher",
        "label": "ZatGo Language Switcher",
        "group": "ui",
        "icon": "globe",
        "description": "English / Arabic switcher.",
        "switch_field": "enable_language_switcher",
    },
    {
        "key": "vansalex_web",
        "label": "ZatGo VanSaleX Web",
        "group": "ui",
        "icon": "link",
        "description": "Serves the VanSaleX web build at /vansalex.",
        "switch_field": "enable_vansalex_web",
        "requires": ("vansalex",),
    },
    {
        "key": "industries",
        "label": "Industries",
        "group": "industries",
        "icon": "organization",
        "description": "Per-site industry packs (restaurant, gym, jewellery, textile ...). Switch them in System Settings -> Industries.",
        "settings": (("ZG System Settings", "Industries (System Settings)"),),
    },
)
