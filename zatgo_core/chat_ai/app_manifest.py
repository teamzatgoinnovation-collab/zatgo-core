"""Hub manifest (services/app_catalog.py)."""

APP = {
    "key": "chat_ai",
    "label": "ZatGo AI",
    "group": "bundled",
    "icon": "bot",
    "description": "ZatGo AI assistant, scheduled AI tasks and the Desk chat sidebar.",
    "color": "#0F766E",
    "clients": ("Desk chat sidebar",),
    "switch_field": "enable_chat_ai",
    "module_def": "Chat AI",
    "workspaces": ("ZatGo AI", "AI Admin", "Chat AI"),
    "settings": (("Chat AI Settings", "Chat AI Settings"),),
}
