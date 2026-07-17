"""App install / migrate / uninstall hooks for ZatGo Core."""

from __future__ import annotations

import frappe

from zatgo_core.plugins.discover import discover_and_register_manifests
from zatgo_core.setup.ensure_desktop import ensure_desktop
from zatgo_core.setup.ensure_roles import ensure_roles
from zatgo_core.setup.seed_defaults import (
    seed_application_settings,
    seed_feature_flags,
    seed_number_series,
    seed_singletons,
)
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")


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
        discover_and_register_manifests()
    except Exception:
        logger.exception("Plugin manifest registration failed")
    try:
        ensure_desktop()
    except Exception:
        logger.exception("Desktop icon / sidebar ensure failed")
    logger.info("zatgo_core after_install completed")


def after_migrate() -> None:
    """Re-assert roles, plugins, and defaults after migrate."""
    ensure_roles()
    seed_singletons()
    seed_number_series()
    seed_feature_flags()
    try:
        seed_application_settings()
    except Exception:
        logger.exception("Application settings seed failed")
    try:
        discover_and_register_manifests()
    except Exception:
        logger.exception("Plugin manifest registration failed")
    try:
        ensure_desktop()
    except Exception:
        logger.exception("Desktop icon / sidebar ensure failed")


def before_uninstall() -> None:
    """Log uninstall; leave audit history intact by default."""
    logger.warning(
        "zatgo_core before_uninstall invoked by %s", frappe.session.user
    )
