"""Frappe hooks for ZatGo Core.

API-only platform hub: whitelist RPC, settings DocTypes, registry.
No Desk pages, workspaces, or module UI — keep invasive overrides rare.
"""

app_name = "zatgo_core"
app_title = "ZatGo Core"
app_publisher = "ZatGo Innovation"
app_description = (
    "ZatGo Core — platform settings, feature flags, integrations, "
    "security, and client RPC hub for Flutter / Electron / Web"
)
app_email = "engineering@zatgo.local"
app_license = "mit"
app_version = "0.2.2"

required_apps = ["erpnext"]

after_install = "zatgo_core.install.after_install"
after_migrate = "zatgo_core.install.after_migrate"
before_uninstall = "zatgo_core.install.before_uninstall"

boot_session = "zatgo_core.events.boot.boot_session"

# Exposes tlv_to_png_data_uri() to print-format Jinja templates. Calling it
# via frappe.get_attr(...) from inside a template works under bench execute
# but is blocked by the sandboxed Jinja environment print formats actually
# render in (frappe.www.printview) — the standard fix is a real jinja method.
jinja = {
    "methods": [
        "zatgo_core.services.zatca_qr.tlv_to_png_data_uri",
    ],
}

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
                    "VanSale User",
                    "VanSale Admin",
                ],
            ]
        ],
    }
]
