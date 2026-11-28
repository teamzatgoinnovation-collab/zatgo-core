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
            ("ZatGo System Settings", "System Settings"),
            ("Application Settings", "Application Settings"),
            ("Integration Settings", "Integrations"),
            # Storage, Security, Payment, Printer and Sync Settings are not listed: nothing reads them yet
            # (docs/SETTINGS.md). Their DocTypes and stored values stay; their forms say so.
            ("ZatGo Notification Settings", "Notifications"),
            ("Number Series Settings", "Number Series"),
            ("Sales Invoice Naming Settings", "Sales Invoice Naming"),
            ("Duplicate Prevention Settings", "Duplicate Prevention"),
            ("Duplicate Rule", "Duplicate Rules"),
            ("Duplicate Override Log", "Duplicate Override Log"),
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
        "icon": "palette",
        "description": "Modern Desk theme and login page.",
        "switch_field": "enable_saas_theme",
        "workspaces": ("ZatGo Desk Theme",),
        "settings": (("Theme Settings", "Theme Settings"),),
    },
    {
        "key": "language_switcher",
        "label": "ZatGo Language Switcher",
        "group": "ui",
        "icon": "globe",
        "description": "English / Arabic switcher.",
        "switch_field": "enable_language_switcher",
        "workspaces": ("ZatGo Language Switcher",),
        "settings": (("Language Settings", "Language Settings"),),
    },
    {
        "key": "vansalex_web",
        "label": "ZatGo VanSaleX Web",
        "group": "ui",
        "icon": "link",
        "description": "Serves the VanSaleX web build at /vansalex.",
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
        # On everywhere it was before it had a switch (a site with no stored value counts as on).
        "switch_field": "enable_zatgo_pos",
        "default_on": True,
        "workspaces": ("ZatGo POS",),
        "settings": (("ZatGo POS Settings", "POS Settings"),),
        # Off: the restaurant and retail POS APIs answer 404. pos_profile / pos_settings stay outside that prefix.
        "api_prefixes": ("zatgo_core.api.v1.resto_pos.", "zatgo_core.api.v1.retail_pos."),
    },
    {
        "key": "duplicate_prevention",
        "label": "Duplicate Prevention",
        "group": "app",
        "icon": "duplicate",
        "description": "Stops duplicate Items, Customers, Suppliers and other masters: blocks strong matches, warns on possible ones, live lookup while typing and smart Link search.",
        # On everywhere it ships (a site with no stored value counts as on); rules are seeded on migrate.
        "switch_field": "enable_duplicate_prevention",
        "default_on": True,
        # Its settings sit in General Settings (platform-wide, like Security / Feature Flags): listed under
        # core_settings below and as shortcuts in workspace/zatgo/zatgo.json -- not owned by an app sidebar.
        # Off: the lookup API answers 404 (Link search and saves are unaffected -- the hooks return at once).
        "api_prefixes": ("zatgo_core.api.v1.duplicate.",),
    },
    {
        "key": "industries",
        "label": "Industries",
        "group": "industries",
        "icon": "organization",
        "description": "Per-site industry packs (restaurant, gym, jewellery, textile ...). Switch them in System Settings -> Industries.",
        "settings": (("ZatGo System Settings", "Industries (System Settings)"),),
    },
)
