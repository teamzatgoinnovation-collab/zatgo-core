"""boot_session enrichment for Desk clients."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core import __version__
from zatgo_core.constants.settings import DOCTYPES
from zatgo_core.industries.gate import enabled_keys
from zatgo_core.services import app_state
from zatgo_core.services.sales_invoice_naming import get_session_user_series


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
    except Exception:
        frappe.logger("zatgo_core").exception("boot_session enrichment failed")
