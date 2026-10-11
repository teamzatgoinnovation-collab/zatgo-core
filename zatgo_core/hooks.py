"""Frappe hooks for ZatGo Core.

Platform hub: whitelist RPC, settings DocTypes, registry, ERPNext
extensions. Also carries what used to be separate apps, each switched per
site in ZG System Settings: the SaaS Desk theme + login page, the language
switcher and the VanSaleX web page (services/ui_apps.py), and the Chat AI,
Tracker and ZatGo Space modules (services/bundled_apps.py).
Keep invasive overrides rare.
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

# SaaS theme / language switcher, switched on per site in ZG System Settings
# (services/ui_apps.py) -- deliberately not app_include_css/js, which would
# load them on every site.
before_request = [
    # Whitelisted methods of switched-off bundled modules -> 404.
    "zatgo_core.services.bundled_apps.gate_module_api",
    "zatgo_core.services.ui_apps.add_desk_includes",
]
page_renderer = ["zatgo_core.services.ui_apps.ThemedLoginPage"]

# Payment Type (Cash/Credit) UX hint -- purely visual, see the files themselves.
doctype_js = {
    "Sales Invoice": "public/js/sales_invoice.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Payment Entry": "public/js/payment_entry.js",
    "Mode of Payment": "public/js/mode_of_payment.js",
    "Journal Entry": "public/js/journal_entry.js",
    # Link from Document Naming to the user-wise Sales Invoice series page.
    "Selling Settings": "public/js/selling_settings.js",
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
        "before_insert": [
            "zatgo_core.services.vansalex_access.check_doc_access",
            "zatgo_core.events.sales_invoice_naming.set_naming_series",
        ],
        "validate": [
            "zatgo_core.events.print_fields.populate_print_fields",
            "zatgo_core.services.payment_allocation.validate_sales_invoice",
        ],
        "on_submit": "zatgo_core.events.sales_invoice_payment.on_submit",
        "before_cancel": "zatgo_core.events.sales_invoice_payment.before_cancel",
    },
    "Purchase Invoice": {
        "before_insert": "zatgo_core.events.return_naming.sync_naming_series",
        "on_submit": "zatgo_core.events.purchase_invoice_payment.on_submit",
        "before_cancel": "zatgo_core.events.purchase_invoice_payment.before_cancel",
    },
    # Multi-method / multi-account payment allocation -- see
    # services/payment_allocation.py and the extend_doctype_class below.
    "Payment Entry": {
        "before_insert": "zatgo_core.services.vansalex_access.check_doc_access",
        "before_validate": [
            "zatgo_core.services.payment_allocation.prepare_payment_entry",
            # A narration the user writes is kept (services/narration.py).
            "zatgo_core.services.narration.keep_user_narration",
        ],
        "validate": "zatgo_core.services.payment_allocation.validate_payment_entry",
    },
    # VanSaleX Modules & Features backstop for field users on any entry
    # point (services/vansalex_access.py); Sales Invoice / Payment Entry above.
    "Sales Order": {"before_insert": "zatgo_core.services.vansalex_access.check_doc_access"},
    # before_save: create AND edit (the app edits through the shared
    # accounting.customers / warehouse.items endpoints).
    "Customer": {"before_save": "zatgo_core.services.vansalex_access.check_doc_access"},
    "Item": {"before_save": "zatgo_core.services.vansalex_access.check_doc_access"},
    "Journal Entry": {"before_validate": "zatgo_core.services.narration.keep_user_narration"},
    "Mode of Payment": {
        "validate": "zatgo_core.services.payment_allocation.validate_mode_of_payment",
    },
    # Chat AI (bundled module): on every doctype, but returns at once on
    # sites where it is switched off (services/bundled_apps.py).
    "*": {
        "after_insert": "zatgo_core.services.bundled_apps.chat_ai_after_insert",
        "on_update": "zatgo_core.services.bundled_apps.chat_ai_on_update",
        "on_submit": "zatgo_core.services.bundled_apps.chat_ai_on_submit",
        "on_cancel": "zatgo_core.services.bundled_apps.chat_ai_on_cancel",
    },
}

# Mixins (Frappe v16) layered over ERPNext's classes -- and over hrms's
# Payment Entry override -- rather than replacing them. Sales Invoice: keep
# an allowed payment-row account instead of resetting it to the mode default.
# Payment Entry: split the bank-side GL line across Payment Details rows.
extend_doctype_class = {
    "Sales Invoice": "zatgo_core.overrides.sales_invoice.ZatGoSalesInvoice",
    "Payment Entry": "zatgo_core.overrides.payment_entry.ZatGoPaymentEntry",
}

scheduler_events = {
    "hourly": [
        "zatgo_core.services.bundled_apps.chat_ai_hourly",
    ],
    "daily": [
        "zatgo_core.services.jobs.daily",
        "zatgo_core.services.bundled_apps.chat_ai_daily",
    ],
}

permission_query_conditions = {
    "ZG Company Settings": "zatgo_core.permissions.company_scope.company_permission_query",
    # Tracker (bundled module): no extra condition where it is switched off.
    "Project": "zatgo_core.services.bundled_apps.tracker_project_query",
    "Task": "zatgo_core.services.bundled_apps.tracker_task_query",
    "Issue": "zatgo_core.services.bundled_apps.tracker_issue_query",
    "Timesheet": "zatgo_core.services.bundled_apps.tracker_timesheet_query",
    "Tracker Activity Session": "zatgo_core.services.bundled_apps.tracker_activity_session_query",
    # Bundled modules' own DocTypes: no rows where the module is switched off.
    "*": "zatgo_core.services.bundled_apps.module_query_conditions",
}

# Tracker (bundled module): no objection (True) where it is switched off --
# never None, which Frappe reads as a denial.
has_permission = {
    "Project": "zatgo_core.services.bundled_apps.tracker_project_has_permission",
    "Task": "zatgo_core.services.bundled_apps.tracker_task_has_permission",
    "Issue": "zatgo_core.services.bundled_apps.tracker_issue_has_permission",
    "Timesheet": "zatgo_core.services.bundled_apps.tracker_timesheet_has_permission",
    "Tracker Activity Session": "zatgo_core.services.bundled_apps.tracker_activity_session_has_permission",
    # Bundled modules' own DocTypes: nobody's where the module is switched off.
    "*": "zatgo_core.services.bundled_apps.module_doc_has_permission",
}

# Old method paths of the merged apps (chat_ai.*, tracker.*, zatgo_space.*)
# -> zatgo_core.<module>.*, for clients built against the old apps.
from zatgo_core.compat_methods import OLD_METHOD_PATHS as override_whitelisted_methods  # noqa: E402



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
                    "ZG Invoice Naming Manager",
                ],
            ]
        ],
    }
]
