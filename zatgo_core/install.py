"""App install / migrate / uninstall hooks for ZatGo Core."""

from __future__ import annotations

import frappe

from zatgo_core.plugins.discover import discover_and_register_manifests
from zatgo_core.setup.ensure_print_formats import ensure_print_formats
from zatgo_core.setup.ensure_roles import ensure_roles
from zatgo_core.setup.ensure_vansale_perms import ensure_vansale_perms
from zatgo_core.setup.seed_defaults import (
    seed_application_settings,
    seed_feature_flags,
    seed_number_series,
    seed_singletons,
)
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

_DESK_SIDEBAR_NAMES = ("ZatGo Core", "Core Administration")
_DESK_PAGE_NAMES = ("zg-core",)
_DESK_ICON_LABELS = ("ZatGo Core",)
_DESK_ICON_APPS = ("zatgo_core",)


def after_install() -> None:
    """Seed roles, singletons, client apps, plugins, and defaults after install."""
    ensure_roles()
    seed_singletons()
    seed_number_series()
    seed_feature_flags()
    try:
        seed_application_settings()
    except Exception:
        logger.exception("Application settings seed failed")
    try:
        ensure_print_formats()
    except Exception:
        logger.exception("Print format seed failed")
    try:
        ensure_vansale_perms()
    except Exception:
        logger.exception("VanSale DocPerm seed failed")
    try:
        discover_and_register_manifests()
    except Exception:
        logger.exception("Plugin manifest registration failed")
    try:
        purge_desk_ui_leftovers()
    except Exception:
        logger.exception("Desk UI leftover purge failed")
    logger.info("zatgo_core after_install completed")


def after_migrate() -> None:
    """Re-assert roles, plugins, and defaults after migrate; purge legacy Desk UI."""
    ensure_roles()
    seed_singletons()
    seed_number_series()
    seed_feature_flags()
    try:
        seed_application_settings()
    except Exception:
        logger.exception("Application settings seed failed")
    try:
        ensure_print_formats()
    except Exception:
        logger.exception("Print format seed failed")
    try:
        ensure_vansale_perms()
    except Exception:
        logger.exception("VanSale DocPerm seed failed")
    try:
        discover_and_register_manifests()
    except Exception:
        logger.exception("Plugin manifest registration failed")
    try:
        purge_desk_ui_leftovers()
    except Exception:
        logger.exception("Desk UI leftover purge failed")


def before_uninstall() -> None:
    """Remove Desk leftovers; leave audit history intact by default."""
    logger.warning(
        "zatgo_core before_uninstall invoked by %s", frappe.session.user
    )
    try:
        purge_desk_ui_leftovers()
    except Exception:
        logger.exception("Desk UI leftover purge failed during uninstall")


def purge_desk_ui_leftovers() -> None:
    """Delete legacy Desktop Icon / Workspace Sidebar / Page rows for Core.

    ZatGo Core is API-only; Desk module UI was removed from the package.
    Records may survive on the site after code deletion.
    """
    deleted = 0

    if frappe.db.exists("DocType", "Desktop Icon"):
        names = set()
        for label in _DESK_ICON_LABELS:
            for row in frappe.get_all(
                "Desktop Icon",
                filters={"label": label},
                pluck="name",
            ):
                names.add(row)
        for app in _DESK_ICON_APPS:
            for row in frappe.get_all(
                "Desktop Icon",
                filters={"app": app},
                pluck="name",
            ):
                names.add(row)
        for name in names:
            frappe.delete_doc("Desktop Icon", name, ignore_permissions=True, force=True)
            deleted += 1

    if frappe.db.exists("DocType", "Workspace Sidebar"):
        for name in _DESK_SIDEBAR_NAMES:
            if frappe.db.exists("Workspace Sidebar", name):
                frappe.delete_doc(
                    "Workspace Sidebar", name, ignore_permissions=True, force=True
                )
                deleted += 1

    if frappe.db.exists("DocType", "Workspace"):
        for name in _DESK_SIDEBAR_NAMES:
            if frappe.db.exists("Workspace", name):
                frappe.delete_doc(
                    "Workspace", name, ignore_permissions=True, force=True
                )
                deleted += 1

    if frappe.db.exists("DocType", "Page"):
        for name in _DESK_PAGE_NAMES:
            if frappe.db.exists("Page", name):
                frappe.delete_doc("Page", name, ignore_permissions=True, force=True)
                deleted += 1

    frappe.clear_cache()
    if deleted:
        logger.info("Purged %s ZatGo Core Desk UI leftover record(s)", deleted)
    else:
        logger.debug("No ZatGo Core Desk UI leftovers found")
