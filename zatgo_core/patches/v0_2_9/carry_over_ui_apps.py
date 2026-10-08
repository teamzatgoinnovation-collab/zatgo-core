"""Carry the old saas_theme / language_switcher (modifyme) / vansalex_web installs over to
the ZG System Settings switches that replace them (services/ui_apps.py).

Runs while the old apps are still installed -- they are uninstalled only
after this migrate -- so a site keeps exactly the look it had: the theme
where saas_theme was installed, the switcher where modifyme or
language_switcher was, /vansalex where vansalex_web was. Only ever switches ON: a site already migrated (or
switched by an admin) is left as it is once the old apps are gone.
"""

from __future__ import annotations

import frappe

SETTINGS = "ZG System Settings"


def execute() -> None:
    if not frappe.db.exists("DocType", SETTINGS):
        return
    frappe.reload_doc("zatgo_core", "doctype", "zg_system_settings")
    installed = set(frappe.get_installed_apps())
    if "saas_theme" in installed:
        frappe.db.set_single_value(SETTINGS, "enable_saas_theme", 1)
    if installed & {"modifyme", "language_switcher"}:
        frappe.db.set_single_value(SETTINGS, "enable_language_switcher", 1)
    if "vansalex_web" in installed:
        frappe.db.set_single_value(SETTINGS, "enable_vansalex_web", 1)
    frappe.clear_document_cache(SETTINGS, SETTINGS)
