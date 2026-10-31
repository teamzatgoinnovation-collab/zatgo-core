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
        "color": "#475569",
        "scoped": ("company", "branch", "user"),
        "clients": ("ZatGo Accounting (desktop)", "ZatGo Accounting (web)"),
        "device": {
            "ZatGo Accounting (desktop)": (
                ("Theme", "Light or dark, kept on this computer."),
            ),
            "ZatGo Accounting (web)": (
                ("Theme", "Light or dark, kept in the browser."),
            ),
        },
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
        "color": "#2F5FEA",
        "scoped": ("user", "role", "warehouse"),
        "clients": ("VanSaleX app (Flutter)", "VanSaleX Web (/vansalex)", "VanSaleX native shell"),
        "device": {
            "VanSaleX app (Flutter)": (
                ("Language", "English or Arabic, chosen in the app."),
                ("Printers", "Name, paper size, copies (1-5) and default printer; ZG Printer Settings is not read."),
                ("Site URL", "The server the app talks to."),
            ),
        },
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
        "icon": "palette",
        "description": "Modern Desk theme and login page.",
        "color": "#C2255C",
        "clients": ("ZatGo Desk",),
        "switch_field": "enable_saas_theme",
        "workspaces": ("ZatGo Desk Theme",),
        "settings": (("ZG Theme Settings", "Theme Settings"),),
    },
    {
        "key": "language_switcher",
        "label": "ZatGo Language Switcher",
        "group": "ui",
        "icon": "globe",
        "description": "English / Arabic switcher.",
        "color": "#0E7490",
        "clients": ("ZatGo Desk",),
        "switch_field": "enable_language_switcher",
        "workspaces": ("ZatGo Language Switcher",),
        "settings": (("ZG Language Settings", "Language Settings"),),
    },
    {
        "key": "vansalex_web",
        "label": "ZatGo VanSaleX Web",
        "group": "ui",
        "icon": "link",
        "description": "Serves the VanSaleX web build at /vansalex.",
        "color": "#0369A1",
        "clients": ("VanSaleX Web (/vansalex)",),
        "switch_field": "enable_vansalex_web",
        "requires": ("vansalex",),
        "workspaces": ("ZatGo VanSaleX Web",),
    },
    {
        "key": "zatgo_pos",
        "label": "ZatGo POS",
        "group": "app",
        "icon": "retail",
        "description": "Point of sale (desktop app): sale defaults, payments and receipts for this site's POS.",
        "color": "#308639",
        "clients": ("ZatGo POS (desktop)",),
        "device": {
            "ZatGo POS (desktop)": (
                ("Tables, orders, kitchen screen", "Toggles that can only narrow what the site allows."),
                ("Receipt printer", "Chosen per terminal."),
                ("Auto-print, silent print, open drawer", "Per terminal."),
                ("Site URL", "The server the app talks to."),
                ("Theme", "Light or dark."),
            ),
        },
        # On everywhere it was before it had a switch (a site with no stored value counts as on).
        "switch_field": "enable_zatgo_pos",
        "default_on": True,
        "workspaces": ("ZatGo POS",),
        "settings": (("ZG POS Settings", "POS Settings"),),
        # Off: the restaurant and retail POS APIs answer 404. pos_profile / pos_settings stay outside that prefix.
        "api_prefixes": ("zatgo_core.api.v1.resto_pos.", "zatgo_core.api.v1.retail_pos."),
    },
    {
        "key": "industries",
        "label": "Industries",
        "group": "industries",
        "icon": "organization",
        "description": "Per-site industry packs (restaurant, gym, jewellery, textile ...). Switch them in System Settings -> Industries.",
        "color": "#B45309",
        "settings": (("ZG System Settings", "Industries (System Settings)"),),
    },
)
