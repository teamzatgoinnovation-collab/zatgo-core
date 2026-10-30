"""Read-only post-migrate check: did this release's schema and data really land on this site?

    bench --site <site> execute zatgo_core.setup.deploy_check.run

Prints one JSON object (`ok` plus each check) and returns it. It only reads -- no document is created or changed
-- so it is safe on a client's site. `accounting.md` asks for the schema to be verified in `information_schema`,
not trusted from the Patch Log: this does that for the columns and indexes this release adds.
"""

from __future__ import annotations

import json

import frappe

SETTINGS = "ZG System Settings"
RELEASE_PATCHES = (
    "zatgo_core.patches.v0_4_7.enable_vansalex_default_on",
    "zatgo_core.patches.v0_4_8.add_warehouse_transfer_point_field",
)
# (table, column) pairs that must carry an index since this release's `search_index` additions
INDEXED = (
    ("tabZG Trip", "sales_user"),
    ("tabZG Trip", "status"),
    ("tabZG Trip", "planned_at"),
    ("tabAI Usage Daily", "user"),
    ("tabAI Usage Daily", "usage_date"),
    ("tabAI Chat Message", "session"),
    ("tabAI Chat Session", "user"),
    ("tabAI Tool Log", "user"),
    ("tabAI Tool Log", "session"),
    ("tabAI Attachment", "session"),
)
# Settings forms that must start with a Tab Break (the Settings items of an app's sidebar, services/app_sidebar.py)
TABBED_FORMS = ("VanSaleX Settings", "Chat AI Settings", "Tracker Settings", "Space Settings", "ZG System Settings")
STAFF_ONLY = (
    "ZG Delivery Boy",
    "ZG Delivery Stop",
    "ZG Vehicle",
    "ZG Service Ticket",
    "ZG Order",
    "ZG Table",
    "ZG KDS Ticket",
)


def _has_index(table: str, column: str) -> bool:
    rows = frappe.db.sql(
        "select 1 from information_schema.STATISTICS where TABLE_SCHEMA = database() and TABLE_NAME = %s "
        "and COLUMN_NAME = %s limit 1",
        (table, column),
    )
    return bool(rows)


def _table_exists(table: str) -> bool:
    return bool(
        frappe.db.sql(
            "select 1 from information_schema.TABLES where TABLE_SCHEMA = database() and TABLE_NAME = %s", (table,)
        )
    )


def collect() -> dict:
    from zatgo_core.services import app_catalog, app_state

    checks: dict[str, object] = {}
    # -- schema -----------------------------------------------------------------
    checks["settings_has_enable_vansalex"] = frappe.get_meta(SETTINGS).has_field("enable_vansalex")
    checks["warehouse_transfer_point_column"] = frappe.db.has_column("Warehouse", "zg_vansalex_transfer_point")
    checks["vansalex_settings_has_max_adjust_qty"] = frappe.get_meta("VanSaleX Settings").has_field("max_adjust_qty")
    checks["patches_logged"] = {p: bool(frappe.db.exists("Patch Log", {"patch": p})) for p in RELEASE_PATCHES}
    missing = [f"{t}.{c}" for t, c in INDEXED if _table_exists(t) and not _has_index(t, c)]
    checks["missing_indexes"] = missing
    # -- data -------------------------------------------------------------------
    stored = frappe.db.sql(
        "select value from `tabSingles` where doctype = %s and field = 'enable_vansalex'", (SETTINGS,)
    )
    checks["enable_vansalex_stored"] = stored[0][0] if stored else None
    checks["vansalex_on"] = app_state.is_on("vansalex")
    checks["app_manifest_errors"] = app_catalog.load_errors()
    bad_category = frappe.db.sql(
        "select name from `tabZG Registered Application` where category not in "
        "('Operations','Sales','Inventory','HR','Finance','Platform','Other')"
    )
    checks["registry_rows"] = frappe.db.count("ZG Registered Application")
    checks["registry_bad_category"] = [r[0] for r in bad_category]
    checks["zatgo_sidebar_exists"] = bool(frappe.db.exists("Workspace Sidebar", "ZatGo"))
    checks["hub_page_exists"] = bool(frappe.db.exists("Page", "zg-app-hub"))
    # -- the sidebars of the apps (ZatGo folder) -------------------------------------
    from zatgo_core.services import app_page, app_sidebar

    checks["enabled_apps_without_sidebar_items"] = [
        app["label"]
        for app in app_page.apps()
        if app_page.is_enabled(app)
        and app_sidebar.desired_items(app)  # an app with neither a Workspace nor settings (MyBis) has no sidebar
        and not frappe.db.count("Workspace Sidebar Item", {"parent": app_sidebar.sidebar_name(app)})
    ]
    checks["sidebar_sections"] = [
        r[0]
        for r in frappe.db.sql(
            "select label from `tabWorkspace Sidebar Item` where parent = 'ZatGo' and type = 'Section Break' order by idx"
        )
    ]
    checks["settings_not_tabbed"] = [
        dt
        for dt in TABBED_FORMS
        if frappe.db.exists("DocType", dt) and frappe.get_meta(dt).fields[0].fieldtype != "Tab Break"
    ]
    from zatgo_core.services import app_desk

    checks["app_rail_icons_visible"] = frappe.get_all(
        "Desktop Icon", filters={"link_to": ["in", app_desk.rail_icon_targets()], "hidden": 0}, pluck="name"
    )
    # -- permissions as the DocType meta resolves them (a site's Custom DocPerm rows replace the shipped ones) --
    checks["staff_only_doctypes_grant_all"] = [
        dt for dt in STAFF_ONLY if any(p.role == "All" for p in frappe.get_meta(dt).permissions)
    ]
    checks["staff_only_doctypes_with_custom_docperm"] = [
        dt for dt in STAFF_ONLY if frappe.db.exists("Custom DocPerm", {"parent": dt})
    ]
    return checks


def verdict(checks: dict) -> bool:
    """Blocking problems only; the *_with_custom_docperm list is informational (a site's own rows win)."""
    return (
        bool(checks["settings_has_enable_vansalex"])
        and bool(checks["warehouse_transfer_point_column"])
        and bool(checks["vansalex_settings_has_max_adjust_qty"])
        and all(checks["patches_logged"].values())
        and not checks["missing_indexes"]
        and checks["enable_vansalex_stored"] is not None
        and not checks["app_manifest_errors"]
        and not checks["registry_bad_category"]
        and bool(checks["zatgo_sidebar_exists"])
        and bool(checks["hub_page_exists"])
        and not checks["enabled_apps_without_sidebar_items"]
        and checks["sidebar_sections"] == ["General Settings"]
        and not checks["settings_not_tabbed"]
        and not checks["app_rail_icons_visible"]
        and not checks["staff_only_doctypes_grant_all"]
    )


def run() -> dict:
    checks = collect()
    result = {"ok": verdict(checks), "site": frappe.local.site, "checks": checks}
    print(json.dumps(result, indent=2, default=str))
    return result
