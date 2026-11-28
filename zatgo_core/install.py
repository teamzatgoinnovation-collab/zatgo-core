"""App install / migrate / uninstall hooks for ZatGo Core."""

from __future__ import annotations

import frappe

from zatgo_core.plugins.discover import discover_and_register_manifests
from zatgo_core.setup.ensure_core_desk import ensure_core_desk
from zatgo_core.setup.ensure_custom_fields import ensure_custom_fields
from zatgo_core.setup.ensure_erp_perms import ensure_erp_perms
from zatgo_core.setup.ensure_mode_of_payment import ensure_mode_of_payment
from zatgo_core.setup.ensure_print_formats import ensure_print_formats
from zatgo_core.setup.ensure_report_print_formats import ensure_report_print_formats
from zatgo_core.setup.ensure_roles import ensure_roles
from zatgo_core.setup.ensure_vansale_perms import ensure_vansale_perms
from zatgo_core.setup.ensure_vansalex_access import ensure_vansalex_access
from zatgo_core.industries.sync import sync_industries
from zatgo_core.licensing.editions import seed_presets
from zatgo_core.licensing.sync import sync_registry
from zatgo_core.services.ui_apps import ensure_ui_apps
from zatgo_core.setup.seed_defaults import (
    seed_application_settings,
    seed_feature_flags,
    seed_number_series,
    seed_singletons,
)
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

SUPPORTED_MAJOR = 16  # Frappe / ERPNext major version this release is tested on

_DESK_SIDEBAR_NAMES = ("ZatGo Core", "Core Administration")
_DESK_PAGE_NAMES = ("zg-core",)
_DESK_ICON_LABELS = ("ZatGo Core",)
_DESK_ICON_APPS = ("zatgo_core",)


def _run_steps(hook: str, steps) -> list[str]:
    """Run each setup step, keep going when one fails, and say so at the end.

    A step that raises is logged and the rest still run (a migrate must not
    be aborted by one optional seed), but the failures are named in one
    ERROR line so a half-set-up site is visible in the log.
    """
    failed: list[str] = []
    for label, step in steps:
        try:
            step()
        except Exception:
            failed.append(label)
            logger.exception("%s: %s failed", hook, label)
    if failed:
        logger.error("zatgo_core %s finished with failed steps: %s", hook, ", ".join(failed))
    return failed


def _ensure_role_profiles() -> None:
    from zatgo_core.setup.ensure_role_profiles import ensure_role_profiles

    ensure_role_profiles()


def _ensure_module_workspaces() -> None:
    from zatgo_core.services.module_workspaces import ensure

    ensure()


def _apply_module_navigation() -> None:
    from zatgo_core.services.module_workspaces import sync_visibility

    sync_visibility()


def _sync_module_settings() -> None:
    from zatgo_core.services.module_settings import sync_rows

    sync_rows()


def _seed_duplicate_rules() -> None:
    from zatgo_core.services.duplicate.defaults import seed_defaults

    seed_defaults()  # fresh sites skip patches; existing ones get them from patches/v0_5_0


# Idempotent steps shared by install and migrate, in order. Each one only adds
# what is missing and never touches customer data (company, accounts, users...).
_SHARED_STEPS = (
    ("custom fields", ensure_custom_fields),
    ("application settings", seed_application_settings),
    ("print formats", ensure_print_formats),
    ("financial statement print formats", ensure_report_print_formats),
    ("Mode of Payment", ensure_mode_of_payment),
    ("VanSale DocPerms", ensure_vansale_perms),
    ("ZatGo Accounts & Inventory rights", ensure_erp_perms),
    ("VanSaleX modules and features", ensure_vansalex_access),
    ("Desk UI leftover purge", lambda: purge_desk_ui_leftovers()),
    ("theme / language switcher", ensure_ui_apps),
    ("industry sync", sync_industries),
    # After the switches are final (ensure_ui_apps): the registry carries each app's real enabled state.
    ("plugin manifest registration", discover_and_register_manifests),
    # After the industry sync: the sidebar lists the enabled industries' workspaces.
    ("ZatGo Desk entry", ensure_core_desk),
    # Edition / licensing vocabulary (licensing/registry.py) -> read-only Module / Feature rows.
    ("licensing registry sync", sync_registry),
    # After the registry sync: one workspace per module (created once), then one Module Settings row per registry module
    # (added enabled, admin choices kept), then each module workspace shown or hidden from those rows.
    ("module workspaces", _ensure_module_workspaces),
    ("module settings", _sync_module_settings),
    ("module navigation", _apply_module_navigation),
    # Access personas as Role Profiles of ERPNext roles (created once, then the site's).
    ("role profiles", _ensure_role_profiles),
    # Licence issuer site only (site_config zg_licence_issuer): create missing preset editions.
    ("preset edition seed", seed_presets),
)


def before_install() -> None:
    """Refuse to install on a Frappe / ERPNext major version this app was not built and tested for."""
    import erpnext

    for name, version in (("Frappe", frappe.__version__), ("ERPNext", erpnext.__version__)):
        try:
            major = int(str(version).split(".")[0])
        except ValueError:
            continue  # unparseable dev version string: do not block
        if major != SUPPORTED_MAJOR:
            frappe.throw(
                f"ZatGo Core supports {name} {SUPPORTED_MAJOR}.x only; this bench has {name} {version}."
            )
    _refuse_doctype_name_collisions()
    _ensure_default_activity_type()


def our_doctype_names() -> list[str]:
    """Every DocType this app ships, read from its JSON files (no database needed)."""
    import json
    import os

    root = frappe.get_app_path("zatgo_core")
    names = []
    for folder, _dirs, files in os.walk(root):
        if os.path.basename(os.path.dirname(folder)) != "doctype":
            continue
        own = os.path.basename(folder) + ".json"
        if own in files:
            with open(os.path.join(folder, own)) as fh:
                data = json.load(fh)
            if data.get("doctype") == "DocType" and data.get("name"):
                names.append(data["name"])
    return sorted(names)


def doctype_name_collisions() -> list[tuple[str, str]]:
    """(DocType, app) for each of our DocType names that another installed app already owns."""
    clashes = []
    for name in our_doctype_names():
        module = frappe.db.get_value("DocType", name, "module")
        if not module:
            continue
        app = frappe.db.get_value("Module Def", module, "app_name")
        if app and app != "zatgo_core":
            clashes.append((name, app))
    return clashes


def _refuse_doctype_name_collisions() -> None:
    """ZatGo DocTypes use plain names (ADR-005), so another app may already own one. Installing over it would
    replace that app's DocType; refuse instead and name each clash."""
    clashes = doctype_name_collisions()
    if clashes:
        listed = ", ".join(f"{name} (owned by {app})" for name, app in clashes)
        frappe.throw(f"ZatGo Core cannot be installed: these DocType names already belong to another app: {listed}.")


def _ensure_default_activity_type() -> None:
    """Make sure the Activity Type "Execution" exists before Frappe initialises the singles.

    Tracker Settings defaults ``default_activity_type`` to "Execution" (a Link). ERPNext's setup wizard
    creates that record, but a site that skipped the wizard has none, and the install then fails with
    "Could not find Default Activity Type: Execution". Creating the standard record is idempotent.
    """
    if not frappe.db.exists("DocType", "Activity Type"):
        return
    if not frappe.db.exists("Activity Type", "Execution"):
        frappe.get_doc({"doctype": "Activity Type", "activity_type": "Execution"}).insert(ignore_permissions=True)


def after_install() -> None:
    """Seed roles, singletons, client apps, plugins, and defaults after install."""
    ensure_roles()
    seed_singletons()
    seed_number_series()
    seed_feature_flags()
    failed = _run_steps("after_install", (("duplicate prevention rules", _seed_duplicate_rules),) + _SHARED_STEPS)
    logger.info("zatgo_core after_install completed%s", f" with {len(failed)} failed step(s)" if failed else "")


def after_migrate() -> None:
    """Re-assert roles, plugins, and defaults after migrate; purge legacy Desk UI."""
    ensure_roles()
    seed_singletons()
    seed_number_series()
    seed_feature_flags()
    _run_steps("after_migrate", _SHARED_STEPS)


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

    The old "ZatGo Core" / "Core Administration" Desk UI was removed from the package; its records may
    survive on the site after code deletion. (The current "ZatGo" entry is rebuilt by ensure_core_desk.)
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
