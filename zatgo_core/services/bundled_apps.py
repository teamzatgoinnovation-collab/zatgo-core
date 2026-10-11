"""Chat AI, Tracker and ZatGo Space -- formerly separate apps, now modules of
zatgo_core (zatgo_core/chat_ai, /tracker, /zatgo_space) switched per site
in ZG System Settings -> Bundled Apps.

zatgo_core runs on every accounting / van-sale site, so nothing of these
modules may act on a site that hasn't switched it on:

- every hook (Chat AI's doc_events on all doctypes and its scheduler jobs,
  Tracker's permission hooks on Project / Task / Issue / Timesheet) goes
  through a wrapper here that returns at once where the module is off;
- no `add_to_apps_screen`: Frappe builds the app's one Apps-screen tile
  from its first entry on every site (create_desktop_icons_from_installed_apps),
  which would turn zatgo_core's tile into Chat AI's -- the modules get their
  Desk icon from their own setup instead;
- their setup (roles, settings, Tracker's Employee custom field and role
  permissions, demo plans) runs only where switched on (`sync_bundled_apps`,
  on migrate and when the settings change);
- their whitelisted API answers 404 (`gate_module_api`, before_request) and
  their documents are nobody's (`module_doc_has_permission` /
  `module_query_conditions`, has_permission / permission_query_conditions
  "*") -- before the merge Frappe refused both as an uninstalled app's;
- their Desk entries (workspace, sidebar, desktop icon) are kept out of the
  synced module folders (`<module>/desk_records/`) and imported only where
  switched on -- switching off removes the entries and the module's Pages,
  never any data;
- their Desk JS/CSS load only where switched on (services/ui_apps.py).

Their DocTypes (tables) exist on every site, empty where unused.
"""

from __future__ import annotations

import os
from functools import lru_cache

import frappe

from zatgo_core.services.ui_apps import switches

# switch key -> (module folder, Module Def, Workspace / Workspace Sidebar names it owns)
BUNDLED = {
    "chat_ai": ("chat_ai", "Chat AI", ("AI Admin", "Chat AI")),
    "tracker": ("tracker", "Tracker", ("Tracker", "Task Management")),
    "zatgo_space": ("zatgo_space", "ZatGo Space", ()),
}


def is_on(key: str) -> bool:
    return bool(switches().get(key))


# -- Chat AI hooks -------------------------------------------------------------


def chat_ai_after_insert(doc, method=None):
    if is_on("chat_ai"):
        from zatgo_core.chat_ai.erpnext.events import document_events

        document_events.after_insert(doc, method)


def chat_ai_on_update(doc, method=None):
    if is_on("chat_ai"):
        from zatgo_core.chat_ai.erpnext.events import document_events

        document_events.on_update(doc, method)


def chat_ai_on_submit(doc, method=None):
    if is_on("chat_ai"):
        from zatgo_core.chat_ai.erpnext.events import document_events

        document_events.on_submit(doc, method)


def chat_ai_on_cancel(doc, method=None):
    if is_on("chat_ai"):
        from zatgo_core.chat_ai.erpnext.events import document_events

        document_events.on_cancel(doc, method)


def chat_ai_hourly():
    if is_on("chat_ai"):
        from zatgo_core.chat_ai.erpnext.events import scheduler_events

        scheduler_events.hourly()


def chat_ai_daily():
    if is_on("chat_ai"):
        from zatgo_core.chat_ai.erpnext.events import scheduler_events

        scheduler_events.daily()


# -- Tracker hooks -------------------------------------------------------------
# Off: "" (no extra condition) / True (no objection) -- Frappe's own
# permissions. NOT None: Frappe's has_controller_permissions reads any falsy
# return (None included) as a denial, for everyone but Administrator.


def _tracker_queries():
    from zatgo_core.tracker.permissions import queries

    return queries


def tracker_project_query(user=None):
    return _tracker_queries().project_permission_query(user) if is_on("tracker") else ""


def tracker_task_query(user=None):
    return _tracker_queries().task_permission_query(user) if is_on("tracker") else ""


def tracker_issue_query(user=None):
    return _tracker_queries().issue_permission_query(user) if is_on("tracker") else ""


def tracker_timesheet_query(user=None):
    return _tracker_queries().timesheet_permission_query(user) if is_on("tracker") else ""


def tracker_activity_session_query(user=None):
    return _tracker_queries().activity_session_permission_query(user) if is_on("tracker") else ""


def tracker_project_has_permission(doc, user=None, permission_type=None):
    if is_on("tracker"):
        return _tracker_queries().project_has_permission(doc, user, permission_type)
    return True


def tracker_task_has_permission(doc, user=None, permission_type=None):
    if is_on("tracker"):
        return _tracker_queries().task_has_permission(doc, user, permission_type)
    return True


def tracker_issue_has_permission(doc, user=None, permission_type=None):
    if is_on("tracker"):
        return _tracker_queries().issue_has_permission(doc, user, permission_type)
    return True


def tracker_timesheet_has_permission(doc, user=None, permission_type=None):
    if is_on("tracker"):
        return _tracker_queries().timesheet_has_permission(doc, user, permission_type)
    return True


def tracker_activity_session_has_permission(doc, user=None, permission_type=None):
    if is_on("tracker"):
        return _tracker_queries().activity_session_has_permission(doc, user, permission_type)
    return True


# -- Switched-off modules: their documents and API ------------------------------

# Module Def -> switch key
MODULE_KEYS = {module: key for key, (_f, module, _n) in BUNDLED.items()}
# Whitelisted-method prefixes of each module: the current path and the old
# app's (still mapped for old clients by override_whitelisted_methods).
METHOD_PREFIXES = {
    key: (f"zatgo_core.{folder}.", f"{folder}.") for key, (folder, _m, _n) in BUNDLED.items()
}


@lru_cache(maxsize=1)
def _doctype_keys() -> dict[str, str]:
    """DocType name -> switch key, read once from the modules' doctype folders
    on disk. The "*" permission hooks run on every permission check of every
    DocType: no frappe.get_meta() there (it would load and cache every
    DocType's meta as a side effect of a permission check)."""
    import json

    out: dict[str, str] = {}
    for key, (folder, _module, _names) in BUNDLED.items():
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), folder, "doctype")
        if not os.path.isdir(base):
            continue
        for n in os.listdir(base):
            path = os.path.join(base, n, f"{n}.json")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    name = json.load(f).get("name")
                if name:
                    out[name] = key
    return out


def _module_key(doctype: str | None) -> str | None:
    return _doctype_keys().get(doctype) if doctype else None


def module_doc_has_permission(doc, ptype=None, user=None):
    """has_permission "*": documents of a switched-off module are nobody's
    (Administrator, migrate and the module's own setup bypass this)."""
    key = _module_key(getattr(doc, "doctype", None))
    return True if key is None else is_on(key)


def module_query_conditions(user=None, doctype=None):
    """permission_query_conditions "*": no rows of a switched-off module."""
    key = _module_key(doctype)
    return "1=0" if key is not None and not is_on(key) else ""


def _requested_method() -> str | None:
    request = getattr(frappe.local, "request", None)
    path = (getattr(request, "path", "") or "").strip("/")
    for prefix in ("api/method/", "api/v1/method/", "api/v2/method/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    form = getattr(frappe.local, "form_dict", None) or {}
    return form.get("cmd") or None


def gate_module_api() -> None:
    """before_request: a whitelisted method of a switched-off module (by its
    zatgo_core path or the old app's) answers 404 -- before the merge Frappe
    refused them on these sites as methods of an uninstalled app; guests
    included (ZatGo Space has allow_guest endpoints)."""
    method = _requested_method()
    if not method:
        return
    for key, prefixes in METHOD_PREFIXES.items():
        if method.startswith(prefixes) and not is_on(key):
            raise frappe.DoesNotExistError(f"{method} is not available on this site")


# -- Desk assets ---------------------------------------------------------------

DESK_ASSETS = {
    "chat_ai": (
        ["chat_ai/css/chat_ai_sidebar.css"],
        ["chat_ai/js/chat_ai_vue.js", "chat_ai/js/chat_ai_sidebar_app.js"],
    ),
    "tracker": (["tracker/css/tracker.css"], ["tracker/js/tracker.js", "tracker/js/tracker_vue.js"]),
}


# -- Setup / teardown per site -------------------------------------------------


def sync_bundled_apps() -> None:
    """after_migrate and on ZG System Settings save: set up what's switched
    on, take the Desk entries away from what's switched off."""
    for key in BUNDLED:
        try:
            if is_on(key):
                enable(key)
            else:
                remove_desk_entries(key)
        except Exception:
            frappe.log_error(title=f"zatgo_core bundled app sync: {key}")


def enable(key: str) -> None:
    folder, _module, _names = BUNDLED[key]
    _import_desk_records(folder)
    bootstrap = frappe.get_attr(f"zatgo_core.{folder}.install.bootstrap")
    bootstrap()


def _module_pages(folder: str) -> list[str]:
    """Page records the module ships (synced by migrate on every site)."""
    base = frappe.get_app_path("zatgo_core", folder, "page")
    if not os.path.isdir(base):
        return []
    return sorted(
        n.replace("_", "-") for n in os.listdir(base) if os.path.isfile(os.path.join(base, n, f"{n}.json"))
    )


def _import_desk_records(folder: str) -> None:
    from frappe.modules.import_file import import_file_by_path

    page_base = frappe.get_app_path("zatgo_core", folder, "page")
    for page in _module_pages(folder):
        n = page.replace("-", "_")
        if not frappe.db.exists("Page", page):
            import_file_by_path(os.path.join(page_base, n, f"{n}.json"), force=True)

    root = frappe.get_app_path("zatgo_core", folder, "desk_records")
    for kind in ("workspace", "workspace_sidebar"):
        base = os.path.join(root, kind)
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for f in files:
                if f.endswith(".json"):
                    import_file_by_path(os.path.join(dirpath, f), force=True)


def remove_desk_entries(key: str) -> None:
    """Workspace, Workspace Sidebar, Desktop Icons and Pages of a
    switched-off module (migrate syncs the Pages onto every site; they would
    sit in every user's awesomebar). Data (its DocTypes' records, settings,
    roles) is never touched."""
    folder, _module, names = BUNDLED[key]
    for page in _module_pages(folder):
        if frappe.db.exists("Page", page):
            # Page.on_trash refuses standard pages outside developer mode;
            # these are metadata rows (migrate re-syncs them, enable()
            # re-imports them), so remove the rows directly.
            frappe.db.delete("Has Role", {"parenttype": "Page", "parent": page})
            frappe.db.delete("Page", page)
    if not names:
        return
    for name in frappe.get_all("Desktop Icon", filters={"link_to": ["in", list(names)]}, pluck="name"):
        frappe.delete_doc("Desktop Icon", name, force=1, ignore_permissions=True)
    for doctype in ("Workspace Sidebar", "Workspace"):
        for name in names:
            if frappe.db.exists(doctype, name):
                frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
