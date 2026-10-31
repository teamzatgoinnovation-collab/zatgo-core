"""The catalog of everything switchable / configurable under zatgo_core.

One source of truth: every module folder of zatgo_core that is a "sub-app"
ships `<folder>/app_manifest.py` with `APP = {...}`; the core's own settings
and Desk-appearance switches are in `plugins/manifests/core_apps.py`. Nothing
here is a hand-kept list -- adding a module = adding its `app_manifest.py`
(the App Settings Hub, `SWITCH_FIELDS` and `BUNDLED` all derive from it).

Pure filesystem + import: no database access, so it is safe at import time
and in the middle of a migrate. Manifests are loaded by file path, not as
packages, so a module's heavy `__init__` is never executed by the scan.

APP keys (only key, label and group are required):
  key            switch / registry key (unique)
  label, icon, description
  group          "bundled" (module folder with its own DocTypes), "app" (an app that lives in the
                 core module, e.g. VanSaleX), "ui" (Desk appearance add-on), "core" (always-on
                 core settings), "industries"
  switch_field   ZG System Settings Check field that turns it on. A bundled app that names none
                 gets `enable_<key>`; an app with no switch is always on.
  default_on     True: a site that has no stored value yet counts the app as ON (an app that was
                 always on before it got a switch -- VanSaleX); the field's JSON default must be 1
                 and a patch stores 1 so the form shows what is enforced.
  module_def     bundled only: Module Def name
  workspaces     Workspace / Sidebar names it owns (the first that exists is its sidebar entry and Overview tab)
  settings       [(DocType, label), ...] its settings DocTypes
  roles          roles that may see it in the hub (default System Manager)
  version        its version (default: zatgo_core's)
  requires       keys of apps that must be on for this one to be switched on
  api_prefixes   whitelisted-method prefixes (end with ".") answered 404 while it is off; a bundled
                 app also gets `zatgo_core.<folder>.` and the old `<folder>.`
  color          "#RRGGBB" accent of the app: Settings Map, popup tile (default slate). White text on it must
                 reach 4.5:1 (tests/unit/test_settings_map.py checks every app)
  scoped         scopes beyond Site its settings can be narrowed to (SCOPES: company, branch, user, role, device,
                 warehouse), shown as scope pills in the Settings Map
  clients        client apps that read its settings (display names)
  device         {client: ((setting, note), ...)} what each client keeps on the device (read-only in the map);
                 every client named here must be in `clients`
"""

from __future__ import annotations

import importlib.util
import logging
import os
from functools import lru_cache
from typing import Any

from zatgo_core import __version__
from zatgo_core.services import settings_palette

logger = logging.getLogger("zatgo_core.app_catalog")

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_MANIFEST = os.path.join(PACKAGE_DIR, "plugins", "manifests", "core_apps.py")
GROUPS = ("core", "app", "ui", "bundled", "industries")
SCOPES = ("site", "company", "branch", "user", "role", "device", "warehouse")


def _load(path: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _strings(app: dict[str, Any], key: str, source: str) -> tuple[str, ...]:
    value = app.get(key) or ()
    if isinstance(value, str) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{source}: {key} must be a list of non-empty strings")
    return tuple(value)


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
    # A bundled module is always switchable: its switch is `enable_<key>` unless it names another.
    out["switch_field"] = app.get("switch_field") or (f"enable_{app['key']}" if app["group"] == "bundled" else None)
    out["default_on"] = bool(app.get("default_on"))
    out["workspaces"] = tuple(app.get("workspaces") or ())
    out["settings"] = tuple((dt, label) for dt, label in app.get("settings") or ())
    out.setdefault("roles", ("System Manager",))
    out["version"] = str(app.get("version") or __version__)
    out["requires"] = _strings(app, "requires", source)
    out["api_prefixes"] = _strings(app, "api_prefixes", source)
    if bad := [p for p in out["api_prefixes"] if not p.endswith(".")]:
        raise ValueError(f"{source}: api_prefixes must end with '.' ({bad[0]!r})")
    out["color"] = app.get("color") or settings_palette.DEFAULT_COLOR
    if not settings_palette.is_hex(out["color"]):
        raise ValueError(f"{source}: color must be #RRGGBB ({out['color']!r})")
    if settings_palette.contrast(out["color"], settings_palette.WHITE) < settings_palette.MIN_CONTRAST:
        raise ValueError(f"{source}: color {out['color']} is too light for white text (needs 4.5:1)")
    out["scoped"] = _strings(app, "scoped", source)
    if bad := [s for s in out["scoped"] if s not in SCOPES or s == "site"]:
        raise ValueError(f"{source}: scoped must be from {SCOPES[1:]} ({bad[0]!r})")
    out["clients"] = _strings(app, "clients", source)
    device = app.get("device") or {}
    if not isinstance(device, dict):
        raise ValueError(f"{source}: device must be {{client: ((setting, note), ...)}}")
    for client, items in device.items():
        if client not in out["clients"]:
            raise ValueError(f"{source}: device client {client!r} is not in clients")
        if not all(isinstance(i, (tuple, list)) and len(i) == 2 and all(isinstance(t, str) and t for t in i) for i in items):
            raise ValueError(f"{source}: device[{client!r}] must be pairs of non-empty strings")
    out["device"] = {c: tuple(tuple(i) for i in items) for c, items in device.items()}
    out["source"] = source
    return out


def module_folders() -> list[str]:
    """Module folders of zatgo_core that ship an app_manifest.py."""
    return sorted(
        d
        for d in os.listdir(PACKAGE_DIR)
        if os.path.isfile(os.path.join(PACKAGE_DIR, d, "app_manifest.py"))
    )


_errors: list[str] = []


def load_errors() -> list[str]:
    """Manifests the last catalog build had to skip (empty when all loaded)."""
    catalog()
    return list(_errors)


@lru_cache(maxsize=None)
def catalog() -> tuple[dict[str, Any], ...]:
    """All apps, core first, then each module folder alphabetically.

    The core file is ours and must load. A MODULE's manifest that is broken
    (syntax error, missing key, duplicate key) is logged and skipped: this is
    imported by ui_apps at import time, so raising here would take every
    request on every site down for one module's typo. The module is then off
    the hub and its switch never reads on; `load_errors()` lists what was
    skipped and tests/integration/test_app_hub.py fails on any.
    """
    _errors.clear()
    apps: list[dict[str, Any]] = []
    core = _load(CORE_MANIFEST, "zatgo_core_core_apps")
    for app in core.APPS:
        apps.append(_normalise(app, "plugins/manifests/core_apps.py"))
    taken = {a["key"] for a in apps}
    for folder in module_folders():
        source = f"{folder}/app_manifest.py"
        try:
            mod = _load(os.path.join(PACKAGE_DIR, folder, "app_manifest.py"), f"zatgo_core_{folder}_manifest")
            app = _normalise(mod.APP, source)
            if app["key"] in taken:
                raise ValueError(f"duplicate app key {app['key']!r}")
        except Exception as exc:
            _errors.append(f"{source}: {exc}")
            logger.error("Skipping broken app manifest %s: %s", source, exc)
            continue
        app["folder"] = folder
        taken.add(app["key"])
        apps.append(app)
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


def settings_doctypes() -> set[str]:
    """Every settings DocType an app lists in its manifest (VanSaleX Settings, Chat AI Settings, ...)."""
    return {dt for a in catalog() for dt, _label in a["settings"]}


def api_prefixes() -> dict[str, tuple[str, ...]]:
    """key -> whitelisted-method prefixes that answer 404 while the app is off: the manifest's own, plus a
    bundled module's current path (`zatgo_core.<folder>.`) and its old app's (`<folder>.`), which old
    clients still call (compat_methods.py)."""
    out: dict[str, tuple[str, ...]] = {}
    for a in catalog():
        prefixes = list(a["api_prefixes"])
        if a["group"] == "bundled":
            prefixes += [f"zatgo_core.{a['folder']}.", f"{a['folder']}."]
        if prefixes:
            out[a["key"]] = tuple(dict.fromkeys(prefixes))
    return out


def dependency_problems(on: dict[str, bool]) -> list[str]:
    """Problems with a switch state: an app that is on while an app it `requires` is off. `on` maps key ->
    bool for every app with a switch; apps without a switch count as on."""
    state = {a["key"]: (bool(on.get(a["key"])) if a["switch_field"] else True) for a in catalog()}
    problems = []
    for a in catalog():
        if not state[a["key"]]:
            continue
        for need in a["requires"]:
            if need in state and not state[need]:
                problems.append(f"{a['label']} needs {get(need)['label']} to be on")
    return problems


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
