"""Hub manifest (services/app_catalog.py)."""

APP = {
    "key": "zatgo_space",
    "label": "ZatGo Space",
    "group": "bundled",
    "icon": "cloud",
    "description": "Space platform: plans, orders and site provisioning.",
    "color": "#4F46E5",
    "clients": ("ZatGo Space (Desk)",),
    "switch_field": "enable_zatgo_space",
    "module_def": "ZatGo Space",
    "workspaces": ("ZatGo Space",),
    "settings": (("Space Settings", "Space Settings"),),
}
