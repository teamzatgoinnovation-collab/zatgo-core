"""Hub manifest (services/app_catalog.py)."""

APP = {
    "key": "tracker",
    "label": "ZatGo Tracker",
    "group": "bundled",
    "icon": "project",
    "description": "Task management, org tree, time tracking and activity sessions.",
    "switch_field": "enable_tracker",
    "module_def": "Tracker",
    "workspaces": ("ZatGo Tracker", "Tracker", "Task Management"),
    "settings": (("Tracker Settings", "Tracker Settings"),),
}
