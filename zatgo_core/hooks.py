"""Frappe hooks for ZatGo Core.

This app is the foundation of the ZatGo ERP ecosystem.
Keep invasive overrides rare; prefer services + whitelisted APIs.
"""

app_name = "zatgo_core"
app_title = "ZatGo Core"
app_publisher = "ZatGo Innovation"
app_description = (
    "ZatGo Core — plugin configuration center, global settings, "
    "feature flags, integrations, security, and client RPC hub"
)
app_email = "engineering@zatgo.local"
app_license = "mit"
app_version = "0.2.0"

required_apps = ["erpnext"]

after_install = "zatgo_core.install.after_install"
after_migrate = "zatgo_core.install.after_migrate"
before_uninstall = "zatgo_core.install.before_uninstall"

app_include_js = [
    "/assets/zatgo_core/js/zg_vue.js",
    "/assets/zatgo_core/js/zatgo_core.js",
]
app_include_css = [
    "/assets/zatgo_core/css/zatgo_core.css",
    "/assets/zatgo_core/css/zg_core_page.css",
]

boot_session = "zatgo_core.events.boot.boot_session"

doc_events = {
    "Company": {
        "after_insert": "zatgo_core.events.company.on_company_update",
        "on_update": "zatgo_core.events.company.on_company_update",
    },
}

scheduler_events = {
    "daily": [
        "zatgo_core.services.jobs.daily",
    ],
}

permission_query_conditions = {
    "ZG Company Settings": "zatgo_core.permissions.company_scope.company_permission_query",
}

fixtures = [
    {
        "dt": "Role",
        "filters": [
            [
                "name",
                "in",
                [
                    "ZG Company Admin",
                    "ZG Branch Admin",
                    "ZG Application Admin",
                    "ZG Read Only",
                ],
            ]
        ],
    }
]

# Export workspace / reports as standard module assets (not fixtures).
