#!/usr/bin/env python3
"""Generate ZatGo Core DocType JSON + Python controllers.

Run from repo root or this directory:
  python3 CustomApps/ZatGoCore/scripts/generate_doctypes.py
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DT_ROOT = ROOT / "zatgo_core" / "zatgo_core" / "doctype"
MODULE = "ZatGo Core"


def field(fieldname: str, fieldtype: str, label: str | None = None, **kwargs) -> dict:
    data = {
        "fieldname": fieldname,
        "fieldtype": fieldtype,
        "label": label or fieldname.replace("_", " ").title(),
    }
    data.update(kwargs)
    return data


def section(name: str, label: str) -> dict:
    return field(name, "Section Break", label)


_COL_SEQ = 0


def col() -> dict:
    global _COL_SEQ
    _COL_SEQ += 1
    return {"fieldname": f"column_break_{_COL_SEQ}", "fieldtype": "Column Break"}


def permissions_admin_write_readonly() -> list[dict]:
    return [
        {
            "role": "System Manager",
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 1,
            "share": 1,
            "print": 1,
            "email": 1,
            "export": 1,
        },
        {
            "role": "ZG Application Admin",
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 0,
            "share": 0,
            "print": 1,
            "email": 1,
            "export": 1,
        },
        {
            "role": "ZG Company Admin",
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 0,
            "share": 0,
            "print": 1,
            "email": 0,
            "export": 1,
        },
        {
            "role": "ZG Branch Admin",
            "read": 1,
            "write": 0,
            "create": 0,
            "delete": 0,
            "print": 1,
            "export": 0,
        },
        {
            "role": "ZG Read Only",
            "read": 1,
            "write": 0,
            "create": 0,
            "delete": 0,
            "print": 1,
            "export": 1,
        },
    ]


def base_doctype(
    name: str,
    fields: list[dict],
    *,
    issingle: int = 0,
    istable: int = 0,
    autoname: str | None = None,
    naming_rule: str | None = None,
    title_field: str | None = None,
    track_changes: int = 1,
    permissions: list[dict] | None = None,
    sort_field: str = "modified",
) -> dict:
    field_order = [f["fieldname"] for f in fields]
    doc = {
        "actions": [],
        "allow_rename": 0 if issingle or istable else 1,
        "creation": "2026-07-16 00:00:00.000000",
        "doctype": "DocType",
        "engine": "InnoDB",
        "field_order": field_order,
        "fields": fields,
        "index_web_pages_for_search": 0,
        "issingle": issingle,
        "istable": istable,
        "links": [],
        "modified": "2026-07-16 00:00:00.000000",
        "modified_by": "Administrator",
        "module": MODULE,
        "name": name,
        "owner": "Administrator",
        "permissions": [] if istable else (permissions or permissions_admin_write_readonly()),
        "sort_field": sort_field,
        "sort_order": "DESC",
        "states": [],
        "track_changes": 0 if istable else track_changes,
    }
    if autoname:
        doc["autoname"] = autoname
    if naming_rule:
        doc["naming_rule"] = naming_rule
    if title_field:
        doc["title_field"] = title_field
    return doc


def write_doctype(slug: str, doc: dict, controller: str) -> None:
    folder = DT_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "__init__.py").write_text("", encoding="utf-8")
    (folder / f"{slug}.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8"
    )
    class_name = "".join(part.title() for part in slug.split("_"))
    py = textwrap.dedent(
        f'''\
        """{doc["name"]} controller."""

        from __future__ import annotations

        {controller}
        '''
    )
    (folder / f"{slug}.py").write_text(py, encoding="utf-8")
    print(f"Wrote {slug}")


def single_controller(class_name: str, validate_body: str = "pass") -> str:
    return textwrap.dedent(
        f'''\
        import frappe
        from frappe.model.document import Document

        from zatgo_core.mixins.auditable import AuditableMixin
        from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


        class {class_name}(AuditableMixin, CacheableSettingsMixin, Document):
            """Singleton settings document."""

            def validate(self) -> None:
                {validate_body}
        '''
    )


def list_controller(class_name: str, validate_body: str = "pass") -> str:
    return textwrap.dedent(
        f'''\
        import frappe
        from frappe.model.document import Document

        from zatgo_core.mixins.auditable import AuditableMixin


        class {class_name}(AuditableMixin, Document):
            """List settings / registry document."""

            def validate(self) -> None:
                {validate_body}
        '''
    )


def child_controller(class_name: str) -> str:
    return textwrap.dedent(
        f'''\
        from frappe.model.document import Document


        class {class_name}(Document):
            """Child table row."""

            pass
        '''
    )


def build_all() -> None:
    DT_ROOT.mkdir(parents=True, exist_ok=True)

    # 1. System Settings (Single)
    write_doctype(
        "zg_system_settings",
        base_doctype(
            "ZG System Settings",
            [
                section("general_section", "General"),
                field("brand_name", "Data", "Brand Name", default="ZatGo"),
                field("company_logo", "Attach Image", "Company Logo"),
                field("theme", "Select", "Theme", options="Light\nDark\nSystem", default="System"),
                col(),
                field("language", "Link", "Language", options="Language"),
                field("timezone", "Data", "Timezone"),
                field("country", "Link", "Country", options="Country"),
                field("currency", "Link", "Currency", options="Currency"),
                field("date_format", "Select", "Date Format",
                      options="yyyy-mm-dd\ndd-mm-yyyy\nmm-dd-yyyy\ndd/mm/yyyy\nmm/dd/yyyy",
                      default="yyyy-mm-dd"),
                section("defaults_section", "Defaults"),
                field("default_company", "Link", "Default Company", options="Company"),
                field("default_warehouse", "Link", "Default Warehouse", options="Warehouse"),
                field("default_cost_center", "Link", "Default Cost Center", options="Cost Center"),
                col(),
                field("fiscal_year", "Link", "Fiscal Year", options="Fiscal Year"),
                field("rounding_method", "Select", "Rounding",
                      options="Banker's Rounding\nCommercial Rounding\nCash Rounding",
                      default="Banker's Rounding"),
                field("rounding_precision", "Int", "Rounding Precision", default=2),
                section("erp_section", "ERP Behaviour"),
                field("enable_multi_company", "Check", "Enable Multi Company", default=1),
                field("enable_branch_mode", "Check", "Enable Branch Mode", default=1),
                field("maintenance_mode", "Check", "Maintenance Mode", default=0),
            ],
            issingle=1,
        ),
        single_controller("ZGSystemSettings", "self._validate_defaults()"),
    )
    # Patch validate helper into system settings file after write — handled in hand-edited file later

    # 2. Company Settings (one per company)
    write_doctype(
        "zg_company_settings",
        base_doctype(
            "ZG Company Settings",
            [
                section("identity_section", "Identity"),
                field("company", "Link", "Company", options="Company", reqd=1, unique=1,
                      in_list_view=1),
                field("is_active", "Check", "Is Active", default=1, in_list_view=1),
                section("tax_section", "Tax"),
                field("default_tax_template", "Data", "Default Tax Template"),
                field("tax_id", "Data", "Tax ID"),
                field("enable_tax_inclusive", "Check", "Tax Inclusive Pricing", default=0),
                section("accounting_section", "Accounting"),
                field("default_receivable_account", "Link", "Default Receivable Account",
                      options="Account"),
                field("default_payable_account", "Link", "Default Payable Account",
                      options="Account"),
                field("default_cash_account", "Link", "Default Cash Account", options="Account"),
                field("default_cost_center", "Link", "Default Cost Center", options="Cost Center"),
                section("inventory_section", "Inventory"),
                field("default_warehouse", "Link", "Default Warehouse", options="Warehouse"),
                field("enable_negative_stock", "Check", "Allow Negative Stock", default=0),
                field("stock_valuation_method", "Select", "Stock Valuation Method",
                      options="FIFO\nMoving Average", default="FIFO"),
                section("sales_section", "Sales"),
                field("default_customer_group", "Link", "Default Customer Group",
                      options="Customer Group"),
                field("default_price_list", "Link", "Default Price List", options="Price List"),
                field("sales_terms", "Text Editor", "Sales Terms"),
                section("purchase_section", "Purchase"),
                field("default_supplier_group", "Link", "Default Supplier Group",
                      options="Supplier Group"),
                field("purchase_terms", "Text Editor", "Purchase Terms"),
                section("pos_section", "POS"),
                field("default_pos_profile", "Data", "Default POS Profile"),
                field("enable_pos", "Check", "Enable POS", default=1),
                section("finance_section", "Finance"),
                field("credit_limit", "Currency", "Credit Limit"),
                field("payment_terms_template", "Data", "Payment Terms Template"),
                section("email_section", "Email"),
                field("company_email", "Data", "Company Email"),
                field("email_footer", "Small Text", "Email Footer"),
                section("branding_section", "Branding"),
                field("logo", "Attach Image", "Logo"),
                field("primary_color", "Color", "Primary Color"),
                field("secondary_color", "Color", "Secondary Color"),
                section("defaults_section", "Defaults"),
                field("default_currency", "Link", "Default Currency", options="Currency"),
                field("default_letter_head", "Link", "Default Letter Head", options="Letter Head"),
            ],
            autoname="field:company",
            naming_rule="By fieldname",
            title_field="company",
        ),
        list_controller(
            "ZGCompanySettings",
            "from zatgo_core.validation.company_settings import validate_company_settings\n"
            "                validate_company_settings(self)",
        ),
    )

    # 3. Branch Settings
    write_doctype(
        "zg_branch_settings",
        base_doctype(
            "ZG Branch Settings",
            [
                section("identity_section", "Identity"),
                field("branch_name", "Data", "Branch Name", reqd=1, in_list_view=1),
                field("company", "Link", "Company", options="Company", reqd=1, in_list_view=1),
                field("erp_branch", "Link", "ERPNext Branch", options="Branch"),
                field("is_active", "Check", "Is Active", default=1, in_list_view=1),
                section("ops_section", "Operations"),
                field("warehouse", "Link", "Warehouse", options="Warehouse"),
                field("pos_profile", "Data", "POS Profile"),
                field("kitchen_enabled", "Check", "Kitchen Enabled", default=0),
                field("cash_counter", "Data", "Cash Counter"),
                field("manager", "Link", "Manager", options="User"),
                section("printers_section", "Printers"),
                field("receipt_printer", "Data", "Receipt Printer"),
                field("kitchen_printer", "Data", "Kitchen Printer"),
                section("shift_section", "Shift Timing"),
                field("shift_start", "Time", "Shift Start"),
                field("shift_end", "Time", "Shift End"),
                field("working_days", "Data", "Working Days", default="Mon,Tue,Wed,Thu,Fri,Sat"),
                section("delivery_section", "Delivery"),
                field("delivery_zone", "Small Text", "Delivery Zone"),
                field("delivery_radius_km", "Float", "Delivery Radius (km)"),
            ],
            autoname="format:BR-{company}-{#####}",
            naming_rule="Expression",
            title_field="branch_name",
        ),
        list_controller(
            "ZGBranchSettings",
            "from zatgo_core.validation.branch_settings import validate_branch_settings\n"
            "                validate_branch_settings(self)",
        ),
    )

    # 4. Application Registry
    write_doctype(
        "zg_application_registry",
        base_doctype(
            "ZG Application Registry",
            [
                section("app_section", "Application"),
                field("app_name", "Data", "App Name", reqd=1, unique=1, in_list_view=1),
                field("module_name", "Data", "Module Name", in_list_view=1),
                field("version", "Data", "Version", in_list_view=1),
                field("enabled", "Check", "Enabled", default=1, in_list_view=1),
                field("app_status", "Select", "App Status",
                      options="Installed\nDisabled\nDeprecated\nPending Update\nError",
                      default="Installed", in_list_view=1),
                section("ui_section", "UI"),
                field("menu_icon", "Data", "Menu Icon"),
                field("workspace", "Data", "Workspace"),
                field("description", "Small Text", "Description"),
                section("meta_section", "Metadata"),
                field("developer", "Data", "Developer", default="ZatGo Innovation"),
                field("depends_on", "Small Text", "Depends On",
                      description="Comma-separated app names"),
                field("minimum_version", "Data", "Minimum Version"),
                field("maximum_version", "Data", "Maximum Version"),
                field("license", "Data", "License", default="MIT"),
                col(),
                field("install_date", "Datetime", "Install Date"),
                field("last_update", "Datetime", "Last Update"),
            ],
            autoname="field:app_name",
            naming_rule="By fieldname",
            title_field="app_name",
        ),
        list_controller(
            "ZGApplicationRegistry",
            "from zatgo_core.validation.app_registry import validate_app_registry\n"
            "                validate_app_registry(self)",
        ),
    )

    # 5. Feature Flag
    write_doctype(
        "zg_feature_flag",
        base_doctype(
            "ZG Feature Flag",
            [
                section("flag_section", "Feature Flag"),
                field("flag_key", "Data", "Flag Key", reqd=1, unique=1, in_list_view=1),
                field("title", "Data", "Title", reqd=1, in_list_view=1),
                field("status", "Select", "Status",
                      options="\n".join(
                          ["Enabled", "Disabled", "Experimental", "Hidden", "Internal", "Beta"]
                      ),
                      default="Disabled", reqd=1, in_list_view=1),
                field("app_name", "Data", "App Name", in_list_view=1),
                field("description", "Small Text", "Description"),
                section("scope_section", "Scope"),
                field("company", "Link", "Company", options="Company"),
                field("branch", "Link", "Branch", options="ZG Branch Settings"),
                field("rollout_percent", "Int", "Rollout Percent", default=100),
                field("is_permanent", "Check", "Is Permanent", default=0),
            ],
            autoname="field:flag_key",
            naming_rule="By fieldname",
            title_field="title",
        ),
        list_controller(
            "ZGFeatureFlag",
            "from zatgo_core.validation.feature_flags import validate_feature_flag\n"
            "                validate_feature_flag(self)",
        ),
    )

    # 6. Integration Settings
    write_doctype(
        "zg_integration_settings",
        base_doctype(
            "ZG Integration Settings",
            [
                section("messaging_section", "Messaging"),
                field("whatsapp_enabled", "Check", "WhatsApp Enabled", default=0),
                field("whatsapp_api_url", "Data", "WhatsApp API URL"),
                field("whatsapp_api_key", "Password", "WhatsApp API Key"),
                field("sms_enabled", "Check", "SMS Enabled", default=0),
                field("sms_gateway", "Data", "SMS Gateway"),
                field("sms_api_key", "Password", "SMS API Key"),
                field("email_enabled", "Check", "Email Enabled", default=1),
                field("default_email_account", "Link", "Default Email Account",
                      options="Email Account"),
                section("push_section", "Push / Chat"),
                field("firebase_enabled", "Check", "Firebase Enabled", default=0),
                field("firebase_project_id", "Data", "Firebase Project ID"),
                field("firebase_credentials_json", "Code", "Firebase Credentials JSON",
                      options="JSON"),
                field("telegram_enabled", "Check", "Telegram Enabled", default=0),
                field("telegram_bot_token", "Password", "Telegram Bot Token"),
                field("slack_enabled", "Check", "Slack Enabled", default=0),
                field("slack_webhook_url", "Password", "Slack Webhook URL"),
                section("maps_section", "Maps"),
                field("google_maps_enabled", "Check", "Google Maps Enabled", default=0),
                field("google_maps_api_key", "Password", "Google Maps API Key"),
                section("ai_section", "AI Providers"),
                field("openai_enabled", "Check", "OpenAI Enabled", default=0),
                field("openai_api_key", "Password", "OpenAI API Key"),
                field("gemini_enabled", "Check", "Gemini Enabled", default=0),
                field("gemini_api_key", "Password", "Gemini API Key"),
                field("claude_enabled", "Check", "Claude Enabled", default=0),
                field("claude_api_key", "Password", "Claude API Key"),
                field("deepseek_enabled", "Check", "DeepSeek Enabled", default=0),
                field("deepseek_api_key", "Password", "DeepSeek API Key"),
                section("api_section", "API / Auth"),
                field("webhooks_enabled", "Check", "Webhooks Enabled", default=1),
                field("rest_api_enabled", "Check", "REST API Enabled", default=1),
                field("graphql_enabled", "Check", "GraphQL Enabled", default=0),
                field("oauth_enabled", "Check", "OAuth Enabled", default=0),
                field("jwt_enabled", "Check", "JWT Enabled", default=0),
                field("jwt_secret", "Password", "JWT Secret"),
            ],
            issingle=1,
            permissions=[
                p for p in permissions_admin_write_readonly()
                if p["role"] in ("System Manager", "ZG Application Admin", "ZG Read Only")
            ],
        ),
        single_controller(
            "ZGIntegrationSettings",
            "from zatgo_core.validation.integrations import validate_integration_settings\n"
            "                validate_integration_settings(self)",
        ),
    )

    # 7. Printer Settings
    write_doctype(
        "zg_printer_settings",
        base_doctype(
            "ZG Printer Settings",
            [
                section("devices_section", "Devices"),
                field("receipt_printer", "Data", "Receipt Printer"),
                field("kitchen_printer", "Data", "Kitchen Printer"),
                field("barcode_printer", "Data", "Barcode Printer"),
                field("label_printer", "Data", "Label Printer"),
                field("a4_printer", "Data", "A4 Printer"),
                section("layout_section", "Layout"),
                field("paper_width_mm", "Int", "Paper Width (mm)", default=80),
                field("copies", "Int", "Copies", default=1),
                field("margin_top", "Int", "Margin Top", default=0),
                field("margin_bottom", "Int", "Margin Bottom", default=0),
                field("margin_left", "Int", "Margin Left", default=0),
                field("margin_right", "Int", "Margin Right", default=0),
                field("logo", "Attach Image", "Logo"),
                section("behaviour_section", "Behaviour"),
                field("auto_print", "Check", "Auto Print", default=0),
                field("silent_print", "Check", "Silent Print", default=0),
            ],
            issingle=1,
        ),
        single_controller("ZGPrinterSettings"),
    )

    # 8. Payment Settings
    write_doctype(
        "zg_payment_settings",
        base_doctype(
            "ZG Payment Settings",
            [
                section("methods_section", "Payment Methods"),
                field("cash_enabled", "Check", "Cash", default=1),
                field("card_enabled", "Check", "Card", default=1),
                field("bank_enabled", "Check", "Bank", default=1),
                field("wallet_enabled", "Check", "Wallet", default=0),
                field("gift_card_enabled", "Check", "Gift Card", default=0),
                field("credit_sale_enabled", "Check", "Credit Sale", default=1),
                section("advanced_section", "Advanced"),
                field("split_payment_enabled", "Check", "Split Payment", default=1),
                field("tips_enabled", "Check", "Tips", default=0),
                field("default_tip_percent", "Percent", "Default Tip Percent"),
                field("service_charge_enabled", "Check", "Service Charge", default=0),
                field("service_charge_percent", "Percent", "Service Charge Percent"),
                field("round_off_enabled", "Check", "Round Off", default=1),
                field("round_off_account", "Link", "Round Off Account", options="Account"),
            ],
            issingle=1,
        ),
        single_controller("ZGPaymentSettings"),
    )

    # 9. Notification Settings
    write_doctype(
        "zg_notification_settings",
        base_doctype(
            "ZG Notification Settings",
            [
                section("channels_section", "Channels"),
                field("desktop_enabled", "Check", "Desktop", default=1),
                field("push_enabled", "Check", "Push", default=0),
                field("email_enabled", "Check", "Email", default=1),
                field("sms_enabled", "Check", "SMS", default=0),
                field("whatsapp_enabled", "Check", "WhatsApp", default=0),
                field("telegram_enabled", "Check", "Telegram", default=0),
                field("slack_enabled", "Check", "Slack", default=0),
                field("in_app_enabled", "Check", "In-App", default=1),
                section("defaults_section", "Defaults"),
                field("default_channel", "Select", "Default Channel",
                      options="Desktop\nEmail\nPush\nIn-App", default="In-App"),
                field("quiet_hours_start", "Time", "Quiet Hours Start"),
                field("quiet_hours_end", "Time", "Quiet Hours End"),
            ],
            issingle=1,
        ),
        single_controller("ZGNotificationSettings"),
    )

    # 10. Storage Settings
    write_doctype(
        "zg_storage_settings",
        base_doctype(
            "ZG Storage Settings",
            [
                section("local_section", "Local Files"),
                field("public_files_path", "Data", "Public Files Path"),
                field("private_files_path", "Data", "Private Files Path"),
                section("cloud_section", "Cloud Providers"),
                field("provider", "Select", "Active Provider",
                      options="Local\nS3\nCloudflare R2\nGoogle Drive\nDropbox\nAzure Blob",
                      default="Local"),
                field("s3_enabled", "Check", "S3 Enabled", default=0),
                field("s3_bucket", "Data", "S3 Bucket"),
                field("s3_region", "Data", "S3 Region"),
                field("s3_access_key", "Password", "S3 Access Key"),
                field("s3_secret_key", "Password", "S3 Secret Key"),
                field("r2_enabled", "Check", "Cloudflare R2 Enabled", default=0),
                field("r2_account_id", "Data", "R2 Account ID"),
                field("r2_bucket", "Data", "R2 Bucket"),
                field("r2_access_key", "Password", "R2 Access Key"),
                field("r2_secret_key", "Password", "R2 Secret Key"),
                field("gdrive_enabled", "Check", "Google Drive Enabled", default=0),
                field("dropbox_enabled", "Check", "Dropbox Enabled", default=0),
                field("azure_enabled", "Check", "Azure Blob Enabled", default=0),
                field("azure_connection_string", "Password", "Azure Connection String"),
                section("backup_section", "Backups"),
                field("backup_enabled", "Check", "Backups Enabled", default=1),
                field("backup_retention_days", "Int", "Backup Retention Days", default=30),
            ],
            issingle=1,
            permissions=[
                p for p in permissions_admin_write_readonly()
                if p["role"] in ("System Manager", "ZG Application Admin", "ZG Read Only")
            ],
        ),
        single_controller("ZGStorageSettings"),
    )

    # 11. Security Settings
    write_doctype(
        "zg_security_settings",
        base_doctype(
            "ZG Security Settings",
            [
                section("password_section", "Password Policy"),
                field("min_password_length", "Int", "Min Password Length", default=10),
                field("require_uppercase", "Check", "Require Uppercase", default=1),
                field("require_number", "Check", "Require Number", default=1),
                field("require_special_char", "Check", "Require Special Character", default=1),
                field("password_expiry_days", "Int", "Password Expiry Days", default=90),
                section("auth_section", "Authentication"),
                field("otp_enabled", "Check", "OTP Enabled", default=0),
                field("two_fa_enabled", "Check", "2FA Enabled", default=0),
                field("session_timeout_minutes", "Int", "Session Timeout (minutes)", default=480),
                field("login_limit", "Int", "Login Limit", default=5),
                field("login_lockout_minutes", "Int", "Login Lockout Minutes", default=15),
                section("access_section", "Access Control"),
                field("allowed_devices", "Small Text", "Allowed Devices"),
                field("allowed_ip", "Small Text", "Allowed IP"),
                field("audit_enabled", "Check", "Audit Enabled", default=1),
                field("encryption_enabled", "Check", "Encryption Enabled", default=1),
                field("api_keys_enabled", "Check", "API Keys Enabled", default=1),
            ],
            issingle=1,
            permissions=[
                p for p in permissions_admin_write_readonly()
                if p["role"] in ("System Manager", "ZG Read Only")
            ],
        ),
        single_controller(
            "ZGSecuritySettings",
            "from zatgo_core.validation.security import validate_security_settings\n"
            "                validate_security_settings(self)",
        ),
    )

    # 12. Sync Settings
    write_doctype(
        "zg_sync_settings",
        base_doctype(
            "ZG Sync Settings",
            [
                section("offline_section", "Offline / Sync"),
                field("offline_mode_enabled", "Check", "Offline Mode", default=0),
                field("sync_interval_seconds", "Int", "Sync Interval (seconds)", default=60),
                field("retry_count", "Int", "Retry Count", default=3),
                field("conflict_strategy", "Select", "Conflict Strategy",
                      options="Server Wins\nClient Wins\nLast Write Wins\nManual",
                      default="Server Wins"),
                field("compression_enabled", "Check", "Compression", default=1),
                field("encryption_enabled", "Check", "Encryption", default=1),
                field("redis_queue", "Data", "Redis Queue", default="default"),
            ],
            issingle=1,
        ),
        single_controller("ZGSyncSettings"),
    )

    # 13a. Number Series Item (child)
    write_doctype(
        "zg_number_series_item",
        base_doctype(
            "ZG Number Series Item",
            [
                field("document_type", "Data", "Document Type", reqd=1, in_list_view=1),
                field("prefix", "Data", "Prefix", reqd=1, in_list_view=1),
                field("series_format", "Data", "Series Format",
                      default=".YYYY.-.#####", in_list_view=1),
                field("current_value", "Int", "Current Value", default=0, in_list_view=1),
                field("padding", "Int", "Padding", default=5),
                field("is_active", "Check", "Is Active", default=1, in_list_view=1),
            ],
            istable=1,
        ),
        child_controller("ZGNumberSeriesItem"),
    )

    # 13b. Number Series Settings
    write_doctype(
        "zg_number_series_settings",
        base_doctype(
            "ZG Number Series Settings",
            [
                section("series_section", "Number Series"),
                field(
                    "series_items",
                    "Table",
                    "Series Items",
                    options="ZG Number Series Item",
                ),
            ],
            issingle=1,
        ),
        single_controller(
            "ZGNumberSeriesSettings",
            "from zatgo_core.validation.number_series import validate_number_series\n"
            "                validate_number_series(self)",
        ),
    )

    # 14. Audit Log
    write_doctype(
        "zg_audit_log",
        base_doctype(
            "ZG Audit Log",
            [
                section("change_section", "Change"),
                field("doctype_name", "Data", "DocType Name", in_list_view=1),
                field("document_name", "Data", "Document Name", in_list_view=1),
                field("fieldname", "Data", "Field", in_list_view=1),
                field("old_value", "Long Text", "Old Value"),
                field("new_value", "Long Text", "New Value"),
                section("actor_section", "Actor"),
                field("changed_by", "Link", "Changed By", options="User", in_list_view=1),
                field("change_date", "Date", "Date", in_list_view=1),
                field("change_time", "Time", "Time"),
                field("ip_address", "Data", "IP Address"),
                field("browser", "Data", "Browser"),
                field("reason", "Small Text", "Reason"),
                field("app_name", "Data", "App Name", in_list_view=1),
            ],
            autoname="AUD-.YYYY.-.#####",
            naming_rule="Expression (old style)",
            track_changes=0,
            permissions=[
                {
                    "role": "System Manager",
                    "read": 1,
                    "write": 0,
                    "create": 1,
                    "delete": 1,
                    "export": 1,
                    "print": 1,
                },
                {
                    "role": "ZG Application Admin",
                    "read": 1,
                    "write": 0,
                    "create": 0,
                    "delete": 0,
                    "export": 1,
                    "print": 1,
                },
                {
                    "role": "ZG Company Admin",
                    "read": 1,
                    "write": 0,
                    "create": 0,
                    "delete": 0,
                    "export": 1,
                    "print": 1,
                },
                {
                    "role": "ZG Read Only",
                    "read": 1,
                    "write": 0,
                    "create": 0,
                    "delete": 0,
                    "export": 1,
                    "print": 1,
                },
            ],
        ),
        textwrap.dedent(
            '''\
            from frappe.model.document import Document


            class ZGAuditLog(Document):
                """Immutable audit trail entry (no client edits expected)."""

                def on_trash(self) -> None:
                    import frappe

                    if "System Manager" not in frappe.get_roles():
                        frappe.throw(frappe._("Only System Manager can delete audit logs"))
            '''
        ),
    )

    # 15. User Preferences
    write_doctype(
        "zg_user_preferences",
        base_doctype(
            "ZG User Preferences",
            [
                section("user_section", "User"),
                field("user", "Link", "User", options="User", reqd=1, unique=1, in_list_view=1),
                field("theme", "Select", "Theme",
                      options="Light\nDark\nSystem", default="System", in_list_view=1),
                field("language", "Link", "Language", options="Language"),
                field("sidebar_collapsed", "Check", "Sidebar Collapsed", default=0),
                section("navigation_section", "Navigation"),
                field("landing_page", "Data", "Landing Page"),
                field("default_dashboard", "Data", "Dashboard"),
                field("shortcuts", "Small Text", "Shortcuts",
                      description="Comma-separated route names"),
                field("favorite_apps", "Small Text", "Favorite Apps"),
                field("recent_documents", "Small Text", "Recent Documents"),
            ],
            autoname="field:user",
            naming_rule="By fieldname",
            title_field="user",
            permissions=[
                {
                    "role": "System Manager",
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "delete": 1,
                    "export": 1,
                },
                {
                    "role": "All",
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "delete": 0,
                    "export": 0,
                },
            ],
        ),
        list_controller("ZGUserPreferences"),
    )

    # Fix system settings controller with helper
    sys_py = DT_ROOT / "zg_system_settings" / "zg_system_settings.py"
    sys_py.write_text(
        textwrap.dedent(
            '''\
            """ZG System Settings controller."""

            from __future__ import annotations

            import frappe
            from frappe.model.document import Document

            from zatgo_core.mixins.auditable import AuditableMixin
            from zatgo_core.mixins.cacheable_settings import CacheableSettingsMixin


            class ZGSystemSettings(AuditableMixin, CacheableSettingsMixin, Document):
                """Global ERP foundation settings for the ZatGo ecosystem."""

                def validate(self) -> None:
                    self._validate_defaults()

                def _validate_defaults(self) -> None:
                    if self.default_warehouse and self.default_company:
                        warehouse_company = frappe.db.get_value(
                            "Warehouse", self.default_warehouse, "company"
                        )
                        if warehouse_company and warehouse_company != self.default_company:
                            frappe.throw(
                                frappe._(
                                    "Default Warehouse must belong to Default Company"
                                )
                            )
            '''
        ),
        encoding="utf-8",
    )
    print("Patched zg_system_settings.py")


if __name__ == "__main__":
    build_all()
