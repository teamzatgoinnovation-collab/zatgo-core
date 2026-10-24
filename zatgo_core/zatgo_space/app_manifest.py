"""Hub manifest (services/app_catalog.py)."""

APP = {
    "key": "zatgo_space",
    "label": "ZatGo Space",
    "group": "bundled",
    "icon": "cloud",
    "description": "Space platform: plans, orders and site provisioning.",
    "switch_field": "enable_zatgo_space",
    "module_def": "ZatGo Space",
    "workspaces": ("ZatGo Space",),
    "settings": (("Space Settings", "Space Settings"),),
}
