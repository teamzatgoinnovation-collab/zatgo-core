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
app_version = "0.2.3"

required_apps = ["erpnext"]

after_install = "zatgo_core.install.after_install"
after_migrate = "zatgo_core.install.after_migrate"
before_uninstall = "zatgo_core.install.before_uninstall"

boot_session = "zatgo_core.events.boot.boot_session"

# Payment Type (Cash/Credit) UX hint -- purely visual, see the files themselves.
doctype_js = {
    "Sales Invoice": "public/js/sales_invoice.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Payment Entry": "public/js/payment_entry.js",
}

# Exposes tlv_to_png_data_uri() to print-format Jinja templates. Calling it
# via frappe.get_attr(...) from inside a template works under bench execute
# but is blocked by the sandboxed Jinja environment print formats actually
# render in (frappe.www.printview) — the standard fix is a real jinja method.
jinja = {
    "methods": [
        "zatgo_core.services.zatca_qr.tlv_to_png_data_uri",
        "zatgo_core.services.zatca_qr.zatca_qr_data_uri",
        "zatgo_core.services.print_tracking.get_copy_label",
        "zatgo_core.services.print_helpers.get_party_default_address",
    ],
}

doc_events = {
    "Company": {
        "after_insert": "zatgo_core.events.company.on_company_update",
        "on_update": "zatgo_core.events.company.on_company_update",
    },
    "Sales Invoice": {
        "before_insert": "zatgo_core.events.return_naming.sync_naming_series",
        "validate": "zatgo_core.events.print_fields.populate_print_fields",
        "on_submit": "zatgo_core.events.sales_invoice_payment.on_submit",
        "before_cancel": "zatgo_core.events.sales_invoice_payment.before_cancel",
    },
    "Purchase Invoice": {
        "before_insert": "zatgo_core.events.return_naming.sync_naming_series",
        "on_submit": "zatgo_core.events.purchase_invoice_payment.on_submit",
        "before_cancel": "zatgo_core.events.purchase_invoice_payment.before_cancel",
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
