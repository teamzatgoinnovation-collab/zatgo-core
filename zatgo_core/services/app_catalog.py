"""The catalog of everything switchable / configurable under zatgo_core.

One source of truth: every module folder of zatgo_core that is a "sub-app"
ships `<folder>/app_manifest.py` with `APP = {...}`; the core's own settings
and Desk-appearance switches are in `plugins/manifests/core_apps.py`. Nothing
here is a hand-kept list -- adding a module = adding its `app_manifest.py`
(the App Settings Hub, `SWITCH_FIELDS` and `BUNDLED` all derive from it).

Pure filesystem + import: no database access, so it is safe at import time
and in the middle of a migrate. Manifests are loaded by file path, not as
packages, so a module's heavy `__init__` is never executed by the scan.

APP keys:
  key            switch / registry key (unique)
  label, icon, description
  group          "bundled" (module with DocTypes), "ui" (Desk appearance),
                 "core" (always on), "industries"
  switch_field   ZG System Settings Check field that turns it on (optional)
  module_def     bundled only: Module Def name
  workspaces     bundled only: Workspace / Sidebar names it owns
  settings       [(DocType, label), ...] its settings DocTypes
  roles          roles that may see it in the hub (default System Manager)
"""

from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from typing import Any

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_MANIFEST = os.path.join(PACKAGE_DIR, "plugins", "manifests", "core_apps.py")
GROUPS = ("core", "ui", "bundled", "industries")


def _load(path: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalise(app: dict[str, Any], source: str) -> dict[str, Any]:
    missing = [k for k in ("key", "label", "group") if not app.get(k)]
    if missing:
        raise ValueError(f"{source}: app manifest lacks {', '.join(missing)}")
    if app["group"] not in GROUPS:
        raise ValueError(f"{source}: unknown group {app['group']!r}")
    if app["group"] == "bundled" and not app.get("module_def"):
        raise ValueError(f"{source}: bundled app needs module_def")
    out = dict(app)
    out.setdefault("icon", "setting")
    out.setdefault("description", "")
    out.setdefault("switch_field", None)
    out["workspaces"] = tuple(app.get("workspaces") or ())
    out["settings"] = tuple((dt, label) for dt, label in app.get("settings") or ())
    out.setdefault("roles", ("System Manager",))
    out["source"] = source
    return out


def module_folders() -> list[str]:
    """Module folders of zatgo_core that ship an app_manifest.py."""
    return sorted(
        d
        for d in os.listdir(PACKAGE_DIR)
        if os.path.isfile(os.path.join(PACKAGE_DIR, d, "app_manifest.py"))
    )


@lru_cache(maxsize=None)
def catalog() -> tuple[dict[str, Any], ...]:
    """All apps, core first, then each module folder alphabetically."""
    apps: list[dict[str, Any]] = []
    core = _load(CORE_MANIFEST, "zatgo_core_core_apps")
    for app in core.APPS:
        apps.append(_normalise(app, "plugins/manifests/core_apps.py"))
    for folder in module_folders():
        mod = _load(os.path.join(PACKAGE_DIR, folder, "app_manifest.py"), f"zatgo_core_{folder}_manifest")
        app = _normalise(mod.APP, f"{folder}/app_manifest.py")
        app["folder"] = folder
        apps.append(app)
    keys = [a["key"] for a in apps]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise ValueError(f"duplicate app keys in catalog: {sorted(dupes)}")
    return tuple(apps)


def get(key: str) -> dict[str, Any] | None:
    return next((a for a in catalog() if a["key"] == key), None)


def switch_fields() -> dict[str, str]:
    """switch key -> ZG System Settings field (the old SWITCH_FIELDS)."""
    return {a["key"]: a["switch_field"] for a in catalog() if a["switch_field"]}


def bundled() -> dict[str, tuple[str, str, tuple[str, ...]]]:
    """key -> (module folder, Module Def, workspaces) (the old BUNDLED)."""
    return {
        a["key"]: (a["folder"], a["module_def"], a["workspaces"])
        for a in catalog()
        if a["group"] == "bundled"
    }


def ensure_switch_fields() -> None:
    """Make sure every switch has its Check field on ZG System Settings.
    The six original switches are in the DocType JSON; a NEW module's field
    is created here as a hidden Custom Field -- the App Settings Hub is where
    it is flipped, so no one has to edit the DocType for a new sub-app."""
    import frappe

    settings = "ZG System Settings"
    meta = frappe.get_meta(settings)
    created = False
    for key, field in switch_fields().items():
        if meta.has_field(field) or frappe.db.exists("Custom Field", {"dt": settings, "fieldname": field}):
            continue
        app = get(key)
        frappe.get_doc(
            {
                "doctype": "Custom Field",
                "dt": settings,
                "fieldname": field,
                "label": f"Enable {app['label']}",
                "fieldtype": "Check",
                "default": "0",
                "hidden": 1,
                "insert_after": "enable_zatgo_space",
            }
        ).insert(ignore_permissions=True)
        created = True
    if created:
        frappe.clear_cache(doctype=settings)
