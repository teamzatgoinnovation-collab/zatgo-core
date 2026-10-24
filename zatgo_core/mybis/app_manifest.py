"""Hub manifest (services/app_catalog.py)."""

APP = {
    "key": "mybis",
    "label": "ZatGo MyBis",
    "group": "app",
    "icon": "chart",
    "description": "Management dashboards and business intelligence for the MyBis app (read-only API).",
    "switch_field": "enable_mybis",
    # Off by default: a site opts in. Off = every zatgo_core.api.v1.mybis.* method answers 404.
    "api_prefixes": ("zatgo_core.api.v1.mybis.",),
}
