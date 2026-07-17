"""DocType names, cache keys, and shared enumerations."""

from __future__ import annotations

DOCTYPES = {
    "SYSTEM_SETTINGS": "ZG System Settings",
    "COMPANY_SETTINGS": "ZG Company Settings",
    "BRANCH_SETTINGS": "ZG Branch Settings",
    "APPLICATION_SETTINGS": "ZG Application Settings",
    "CLIENT_APPLICATION": "ZG Client Application",
    "APPLICATION_REGISTRY": "ZG Application Registry",  # legacy list; prefer Application Settings
    "REGISTERED_APPLICATION": "ZG Registered Application",
    "SETTING_SECTION": "ZG Setting Section",
    "CONFIG_PROFILE": "ZG Config Profile",
    "CONFIG_HISTORY": "ZG Config History",
    "FEATURE_FLAG": "ZG Feature Flag",
    "INTEGRATION_SETTINGS": "ZG Integration Settings",
    "PRINTER_SETTINGS": "ZG Printer Settings",
    "PAYMENT_SETTINGS": "ZG Payment Settings",
    "NOTIFICATION_SETTINGS": "ZG Notification Settings",
    "STORAGE_SETTINGS": "ZG Storage Settings",
    "SECURITY_SETTINGS": "ZG Security Settings",
    "SYNC_SETTINGS": "ZG Sync Settings",
    "NUMBER_SERIES_SETTINGS": "ZG Number Series Settings",
    "NUMBER_SERIES_ITEM": "ZG Number Series Item",
    "AUDIT_LOG": "ZG Audit Log",
    "USER_PREFERENCES": "ZG User Preferences",
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
