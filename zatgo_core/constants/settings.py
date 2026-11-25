"""DocType names, cache keys, and shared enumerations."""

from __future__ import annotations

DOCTYPES = {
    "SYSTEM_SETTINGS": "ZatGo System Settings",
    "COMPANY_SETTINGS": "Company Settings",
    "BRANCH_SETTINGS": "Branch Settings",
    "APPLICATION_SETTINGS": "Application Settings",
    "CLIENT_APPLICATION": "Client Application",
    "APPLICATION_REGISTRY": "Application Registry",  # legacy list; prefer Application Settings
    "REGISTERED_APPLICATION": "Registered Application",
    "SETTING_SECTION": "Setting Section",
    "CONFIG_PROFILE": "Config Profile",
    "CONFIG_HISTORY": "Config History",
    "FEATURE_FLAG": "Feature Flag",
    "INTEGRATION_SETTINGS": "Integration Settings",
    "PRINTER_SETTINGS": "Printer Settings",
    "PAYMENT_SETTINGS": "Payment Settings",
    "NOTIFICATION_SETTINGS": "ZatGo Notification Settings",
    "STORAGE_SETTINGS": "Storage Settings",
    "SECURITY_SETTINGS": "ZatGo Security Settings",
    "SYNC_SETTINGS": "Sync Settings",
    "NUMBER_SERIES_SETTINGS": "Number Series Settings",
    "NUMBER_SERIES_ITEM": "Number Series Item",
    "AUDIT_LOG": "Audit Log",
    "USER_PREFERENCES": "User Preferences",
}

SINGLE_SETTINGS = (
    DOCTYPES["SYSTEM_SETTINGS"],
    DOCTYPES["APPLICATION_SETTINGS"],
    DOCTYPES["INTEGRATION_SETTINGS"],
    DOCTYPES["PRINTER_SETTINGS"],
    DOCTYPES["PAYMENT_SETTINGS"],
    DOCTYPES["NOTIFICATION_SETTINGS"],
    DOCTYPES["STORAGE_SETTINGS"],
    DOCTYPES["SECURITY_SETTINGS"],
    DOCTYPES["SYNC_SETTINGS"],
    DOCTYPES["NUMBER_SERIES_SETTINGS"],
)

FEATURE_FLAG_STATUSES = (
    "Enabled",
    "Disabled",
    "Experimental",
    "Hidden",
    "Internal",
    "Beta",
)

CACHE_TTL_SECONDS = 300

CACHE_KEYS = {
    "SYSTEM": "zg_core:system_settings",
    "COMPANY": "zg_core:company_settings:{company}",
    "BRANCH": "zg_core:branch_settings:{branch}",
    "USER_PREFS": "zg_core:user_preferences:{user}",
    "FEATURE_FLAGS": "zg_core:feature_flags",
    "APP_REGISTRY": "zg_core:application_settings",
    "INTEGRATIONS": "zg_core:integrations",
    "PRINTERS": "zg_core:printers",
}
