"""Hub manifest (services/app_catalog.py)."""

APP = {
    "key": "chat_ai",
    "label": "ZatGo AI",
    "group": "bundled",
    "icon": "bot",
    "description": "ZatGo AI assistant, scheduled AI tasks and the Desk chat sidebar.",
    "switch_field": "enable_chat_ai",
    "module_def": "Chat AI",
    "workspaces": ("AI Admin", "Chat AI", "ZatGo AI"),
    "settings": (("Chat AI Settings", "Chat AI Settings"),),
}
