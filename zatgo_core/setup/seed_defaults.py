"""Seed singleton settings and default number series / feature flags."""

from __future__ import annotations

import frappe

from zatgo_core.constants.settings import DOCTYPES, SINGLE_SETTINGS
from zatgo_core.repositories.settings_repository import SettingsRepository
from zatgo_core.utils.logging import get_logger
from zatgo_core.validation.number_series import DEFAULT_DOCUMENT_TYPES

logger = get_logger("system")

DEFAULT_FEATURE_FLAGS = (
    ("zatgo.offline_mode", "Offline Mode", "Disabled", "zatgo_core"),
    ("zatgo.ai.assistant", "AI Assistant", "Beta", "zatgo_ai"),
    ("zatgo.pos.split_payment", "POS Split Payment", "Enabled", "zatgo_pos"),
    ("zatgo.kitchen.kds", "Kitchen Display", "Enabled", "zatgo_kitchen"),
    ("zatgo.delivery.tracking", "Delivery Tracking", "Experimental", "zatgo_delivery"),
)


def seed_singletons() -> None:
    """Ensure all single settings DocTypes exist."""
    for doctype in SINGLE_SETTINGS:
        if not frappe.db.exists("DocType", doctype):
            logger.warning("DocType %s missing; skip seed", doctype)
            continue
        SettingsRepository.get_single(doctype)
        logger.info("Ensured singleton %s", doctype)


def seed_number_series() -> None:
    """Populate default series rows when empty."""
    doctype = DOCTYPES["NUMBER_SERIES_SETTINGS"]
    if not frappe.db.exists("DocType", doctype):
        return
    doc = SettingsRepository.get_single(doctype)
    if doc.get("series_items"):
        return
    prefix_map = {
        "Sales Invoice": "ZG-SINV-",
        "Purchase Invoice": "ZG-PINV-",
        "POS Invoice": "ZG-POS-",
        "Quotation": "ZG-QTN-",
        "Delivery Note": "ZG-DN-",
        "Payment Entry": "ZG-PE-",
        "Journal Entry": "ZG-JE-",
        "Project": "ZG-PROJ-",
        "Task": "ZG-TASK-",
        "Employee": "ZG-EMP-",
        "Customer": "ZG-CUST-",
        "Supplier": "ZG-SUP-",
        "Stock Entry": "ZG-STE-",
        "Work Order": "ZG-WO-",
        "Production": "ZG-PRD-",
    }
    for document_type in DEFAULT_DOCUMENT_TYPES:
        doc.append(
            "series_items",
            {
                "document_type": document_type,
                "prefix": prefix_map.get(document_type, "ZG-DOC-"),
                "series_format": ".YYYY.-.#####",
                "current_value": 0,
                "padding": 5,
                "is_active": 1,
            },
        )
    doc.flags.ignore_zg_audit = True
    doc.save(ignore_permissions=True)
    logger.info("Seeded default number series")


def seed_feature_flags() -> None:
    """Create baseline feature flags if missing."""
    if not frappe.db.exists("DocType", DOCTYPES["FEATURE_FLAG"]):
        return
    for flag_key, title, status, app_name in DEFAULT_FEATURE_FLAGS:
        if frappe.db.exists(DOCTYPES["FEATURE_FLAG"], flag_key):
            continue
        frappe.get_doc(
            {
                "doctype": DOCTYPES["FEATURE_FLAG"],
                "flag_key": flag_key,
                "title": title,
                "status": status,
                "app_name": app_name,
                "rollout_percent": 100,
                "description": f"Default flag for {title}",
            }
        ).insert(ignore_permissions=True)
    logger.info("Seeded default feature flags")


def seed_application_settings() -> None:
    """Ensure site Application Settings exist with default Electron/Flutter/Web clients."""
    if not frappe.db.exists("DocType", DOCTYPES["APPLICATION_SETTINGS"]):
        logger.warning("ZG Application Settings missing; skip seed")
        return
    SettingsRepository.get_single(DOCTYPES["APPLICATION_SETTINGS"])
    from zatgo_core.services.app_registry_service import AppRegistryService

    AppRegistryService.sync_installed_apps(ignore_permissions=True)
    logger.info("Seeded application settings client apps")
