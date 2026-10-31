"""Hub manifest (services/app_catalog.py)."""

APP = {
    "key": "tracker",
    "label": "ZatGo Tracker",
    "group": "bundled",
    "icon": "project",
    "description": "Task management, org tree, time tracking and activity sessions.",
    "color": "#1B4D3E",
    "scoped": ("role",),
    "clients": ("ZatGo Tracker (Desk)",),
    "switch_field": "enable_tracker",
    "module_def": "Tracker",
    "workspaces": ("ZatGo Tracker", "Tracker", "Task Management"),
    "settings": (("Tracker Settings", "Tracker Settings"),),
}
