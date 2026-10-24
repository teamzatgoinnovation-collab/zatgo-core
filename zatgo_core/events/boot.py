"""boot_session enrichment for Desk clients."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core import __version__
from zatgo_core.constants.settings import DOCTYPES
from zatgo_core.industries.gate import enabled_keys
from zatgo_core.services import app_page, app_state, core_sidebar
from zatgo_core.services.sales_invoice_naming import get_session_user_series


def _route_sidebar_entries(bootinfo: Any) -> None:
    """Point each app's entry in the ZatGo sidebar at its page (`/desk/zg-app/<app>`).

    The entry stays a Workspace link -- so whether a user sees it is still decided by that Workspace's roles --
    and Frappe's sidebar navigates to an item's `route` when it has one (frappe/public/js/frappe/ui/sidebar/
    sidebar_item.js, also used for the rail icon). Frappe never fills `route` itself; if a Frappe update stops
    honouring it the entry simply opens the Workspace as before.
    """
    sidebars = bootinfo.get("workspace_sidebar_item") or {}
    sidebar = sidebars.get(core_sidebar.NAME.lower())
    if not sidebar:
        return
    routes = app_page.workspace_routes()
    for item in sidebar.get("items", []):
        if item.get("link_type") == "Workspace" and item.get("link_to") in routes:
            item["route"] = routes[item["link_to"]]


def boot_session(bootinfo: Any) -> None:
    """Inject compact ZatGo Core boot payload for Desk / Vue clients."""
    try:
        system = {}
        if frappe.db.exists("DocType", DOCTYPES["SYSTEM_SETTINGS"]):
            if frappe.db.exists(DOCTYPES["SYSTEM_SETTINGS"], DOCTYPES["SYSTEM_SETTINGS"]):
                doc = frappe.get_cached_doc(
                    DOCTYPES["SYSTEM_SETTINGS"], DOCTYPES["SYSTEM_SETTINGS"]
                )
                system = {
                    "brand_name": doc.get("brand_name"),
                    "theme": doc.get("theme"),
                    "default_company": doc.get("default_company"),
                    "maintenance_mode": doc.get("maintenance_mode"),
                    "autofill_payment_accounts": doc.get("autofill_payment_accounts"),
                    "enable_ifrs_reports": doc.get("enable_ifrs_reports"),
                }

        flags = []
        if frappe.db.exists("DocType", DOCTYPES["FEATURE_FLAG"]):
            flags = frappe.get_all(
                DOCTYPES["FEATURE_FLAG"],
                filters={"status": ("in", ["Enabled", "Beta", "Experimental", "Internal"])},
                fields=["flag_key", "status", "app_name"],
                limit_page_length=200,
            )

        bootinfo.zatgo_core = {
            "system": system,
            "feature_flags": flags,
            "version": __version__,
            # The ZatGo > Apps pages (services/app_page.py): old Desk URL of an app's Workspace -> its page,
            # and settings DocType -> app route key (the settings form shows an "Overview" tab back to it).
            "app_routes": app_page.old_url_redirects(),
            "app_settings": app_page.settings_routes(),
            # Apps with a switch that are on for this site (UI hint only; the server enforces,
            # services/app_gate.py).
            "apps": sorted(key for key, on in app_state.switches().items() if on),
            # Industries switched on for this site (UI hint only; the
            # server enforces, industries/gate.py).
            "industries": sorted(enabled_keys()),
            # This user's own invoice/return series per company, for the
            # Sales Invoice form (public/js/sales_invoice.js).
            "sales_invoice_naming": get_session_user_series(),
        }
        _route_sidebar_entries(bootinfo)
    except Exception:
        frappe.logger("zatgo_core").exception("boot_session enrichment failed")
