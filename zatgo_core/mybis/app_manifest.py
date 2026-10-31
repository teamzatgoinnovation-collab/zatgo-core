"""Hub manifest (services/app_catalog.py)."""

APP = {
    "key": "mybis",
    "label": "ZatGo MyBis",
    "group": "app",
    "icon": "chart",
    "description": "Management dashboards and business intelligence for the MyBis app (read-only API).",
    "color": "#8430CE",
    "scoped": ("user",),
    "clients": ("MyBis app (Flutter)",),
    "device": {
        "MyBis app (Flutter)": (
            ("Theme, date format, decimals, currency position", "Display choices, kept on the device."),
            ("Default company and default period", "The user's own pick wins over the site default."),
            ("Auto-refresh and alerts", "Interval, alerts on or off and the lowest severity."),
            ("KPI cards", "Which of the 9 cards show."),
            ("Export format and offline copy", "Kept on the device; not controlled by the site yet."),
            ("Server URL", "The server the app talks to."),
        ),
    },
    "switch_field": "enable_mybis",
    "workspaces": ("ZatGo MyBis",),
    "settings": (("ZG MyBis Settings", "MyBis Settings"),),
    # Off by default: a site opts in. Off = every zatgo_core.api.v1.mybis.* method answers 404.
    "api_prefixes": ("zatgo_core.api.v1.mybis.",),
}
