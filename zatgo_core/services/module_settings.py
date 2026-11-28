"""ZatGo modules a site uses (Phase 5, ADR-003): the rules behind the Module Settings DocType.

A module is a licensing-registry module (licensing/registry.py: sales, procurement, inventory, accounting, pos,
vansalex, crm, production, ...). Module Settings keeps one row per module: enabled, order, icon, workspace and the
settings DocType that configures it. The registry stays the truth for what a module contains and needs.

Four states, kept apart (MODULE_DEPENDENCIES.md):
- **installed**: the module's app is installed on this site (`source_app`)
- **enabled**: its row here is ticked (no row, or no DocType yet, counts as enabled; nothing changes on upgrade)
- **licensed**: licensing/gate.py (always true while no licence is enforced)
- **authorized**: roles, DocPerms and User Permissions, per document

Switching a module off:
- its ZatGo whitelisted methods answer 404 (`gate_api`, called by services/app_gate.py)
- writes to the ZatGo DocTypes only it covers are refused; reading stays allowed (`doc_has_permission`)
- apps and industries that only it covers count as off (`app_allowed`, `industry_allowed`), so their sidebars,
  folders and gates follow
- **never** deletes data, and never touches ERPNext's own DocTypes: ERPNext core keeps working as ERPNext
  permissions allow

Only a System Manager may switch a module (as with app switches, services/app_authority.py). A module that an
enabled module needs cannot be switched off; one whose needs are off cannot be switched on. Dependencies are
reported, never switched on automatically.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

DOCTYPE = "Module Settings"
ROW_DOCTYPE = "Module Setting"
ALWAYS_ON = frozenset({"foundation"})
WRITE_ACTIONS = frozenset({"create", "write", "delete", "submit", "cancel", "amend", "import"})
_LOCAL = "zg_module_settings_cache"


# -- the registry side (code, no database) ------------------------------------------------------------------------

def _registry():
    from zatgo_core.licensing import registry

    return registry


def _live_features(module_id: str):
    return [f for f in _registry().features_of_module(module_id) if not f.retired]


def dependencies() -> dict[str, set[str]]:
    """module id -> the other modules its features need (foundation left out: it is always on)."""
    reg = _registry()
    out: dict[str, set[str]] = {}
    for module in reg.modules():
        needed: set[str] = set()
        for feature in _live_features(module.id):
            for feature_id, _actions in feature.requires:
                required = reg.get_feature(feature_id)
                if required is not None:
                    needed.add(required.module)
        out[module.id] = needed - {module.id} - ALWAYS_ON
    return out


def dependents(module_id: str) -> set[str]:
    return {m for m, needs in dependencies().items() if module_id in needs}


# -- the site side ---------------------------------------------------------------------------------------------------

def _cache() -> dict[str, Any]:
    cache = getattr(frappe.local, _LOCAL, None)
    if cache is None:
        cache = {}
        setattr(frappe.local, _LOCAL, cache)
    return cache


def _rows() -> list[Any]:
    try:
        return list(frappe.get_cached_doc(DOCTYPE).get("modules") or [])
    except Exception:  # before the first migrate, or mid-migrate
        return []


def disabled_modules() -> frozenset[str]:
    """Modules switched off on this site (cached for the request)."""
    cache = _cache()
    if "disabled" not in cache:
        cache["disabled"] = frozenset(r.module for r in _rows() if not r.enabled) - ALWAYS_ON
    return cache["disabled"]


def is_enabled(module_id: str) -> bool:
    return module_id not in disabled_modules()


def shows_in_navigation(module_id: str) -> bool:
    """Its row's "Show in navigation" (no row: shown). Navigation only: an enabled module whose workspace is hidden
    still works through its documents and API."""
    cache = _cache()
    if "hidden_nav" not in cache:
        cache["hidden_nav"] = frozenset(r.module for r in _rows() if not int(r.get("show_in_navigation") if r.get("show_in_navigation") is not None else 1))
    return module_id not in cache["hidden_nav"]


def is_installed(module_id: str) -> bool:
    module = _registry().get_module(module_id)
    return bool(module) and (module.source_app in frappe.get_installed_apps())


def after_change() -> None:
    """After a save: forget the request cache so every gate sees the new state at once."""
    setattr(frappe.local, _LOCAL, None)


def apply_navigation() -> None:
    """After a Module Settings save: show / hide the module workspaces, their sidebars and icons."""
    from zatgo_core.services import module_workspaces

    after_change()
    module_workspaces.sync_visibility()
    frappe.clear_cache()


def _covering(attribute: str, value: str) -> set[str]:
    """Modules whose live features name `value` in `attribute` (app_key / industry)."""
    return {f.module for f in _registry().features() if not f.retired and getattr(f, attribute) == value}


def app_allowed(app_key: str) -> bool:
    """False only when every module that covers the app is switched off (an app no module names is allowed)."""
    disabled = disabled_modules()
    if not disabled:
        return True
    covering = _covering("app_key", app_key)
    return not covering or not covering <= disabled


def industry_allowed(industry_key: str) -> bool:
    disabled = disabled_modules()
    if not disabled:
        return True
    covering = _covering("industry", industry_key)
    return not covering or not covering <= disabled


def blocked_api_prefixes() -> tuple[str, ...]:
    """Whitelisted-method prefixes of switched-off modules that no enabled module also claims."""
    disabled = disabled_modules()
    if not disabled:
        return ()
    cache = _cache()
    if "prefixes" not in cache:
        off, on = set(), set()
        for feature in _registry().features():
            if feature.retired:
                continue
            (off if feature.module in disabled else on).update(feature.api_prefixes)
        cache["prefixes"] = tuple(sorted(off - on))
    return cache["prefixes"]


def _app_doctypes() -> frozenset[str]:
    cache = _cache()
    if "app_doctypes" not in cache:
        modules = frappe.get_all("Module Def", filters={"app_name": "zatgo_core"}, pluck="name")
        cache["app_doctypes"] = frozenset(frappe.get_all("DocType", filters={"module": ["in", modules]}, pluck="name"))
    return cache["app_doctypes"]


def blocked_doctypes() -> frozenset[str]:
    """ZatGo-owned DocTypes that only switched-off modules cover. ERPNext's DocTypes are never in this set."""
    disabled = disabled_modules()
    if not disabled:
        return frozenset()
    cache = _cache()
    if "doctypes" not in cache:
        off, on = set(), set()
        for feature in _registry().features():
            if feature.retired:
                continue
            (off if feature.module in disabled else on).update(g.doctype for g in feature.doctypes)
        cache["doctypes"] = frozenset((off - on) & _app_doctypes())
    return cache["doctypes"]


def gate_api(method: str) -> None:
    """Called from services/app_gate.gate_api: a method of a switched-off module answers 404."""
    for prefix in blocked_api_prefixes():
        if method.startswith(prefix):
            raise frappe.DoesNotExistError(f"{method} is not available on this site")


def doc_has_permission(doc: Any = None, ptype: str | None = None, user: str | None = None, **kwargs: Any) -> bool:
    """has_permission "*": refuse writes to a ZatGo DocType whose module is switched off. Always True or False
    (None would read as a denial)."""
    if ptype not in WRITE_ACTIONS or not disabled_modules():
        return True
    doctype = getattr(doc, "doctype", None) or (doc if isinstance(doc, str) else None) or kwargs.get("doctype")
    return doctype not in blocked_doctypes()


# -- rows and validation -------------------------------------------------------------------------------------------

def _labels(module_ids: set[str]) -> str:
    reg = _registry()
    return "\n".join(sorted((reg.get_module(m).label if reg.get_module(m) else m) for m in module_ids))


def _default_workspace(module_id: str) -> str | None:
    from zatgo_core.services import module_workspaces

    own = module_workspaces.name_for_module(module_id)
    if own and frappe.db.exists("Workspace", own):
        return own
    for feature in _live_features(module_id):
        for name in feature.workspaces:
            if frappe.db.exists("Workspace", name):
                return name
    return None


def sync_rows() -> bool:
    """One row per registry module, added enabled; registry fields refreshed; a site admin's choices (enabled,
    order, icon, workspace, configuration) kept. Writes only when something changed. Returns whether it saved."""
    if not frappe.db.exists("DocType", DOCTYPE):
        return False
    doc = frappe.get_doc(DOCTYPE)
    deps = dependencies()
    installed = set(frappe.get_installed_apps())
    by_module = {r.module: r for r in doc.get("modules") or []}
    changed = False
    for module in sorted(_registry().modules(), key=lambda m: (m.order, m.id)):
        row = by_module.get(module.id)
        if row is None:
            row = doc.append("modules", {"module": module.id, "enabled": 1, "show_in_navigation": 1, "display_order": module.order,
                                          "icon": module.icon, "workspace": _default_workspace(module.id)})
            changed = True
        wanted = {
            "module_label": module.label,
            "depends_on": _labels(deps.get(module.id, set())),
            "installed": 1 if module.source_app in installed else 0,
            "source_app": module.source_app,
            "description": module.description,
        }
        if module.id in ALWAYS_ON and not row.enabled:
            wanted["enabled"] = 1
        if not row.workspace and _default_workspace(module.id):
            wanted["workspace"] = _default_workspace(module.id)
        for key, value in wanted.items():
            current = row.get(key)
            same = int(current or 0) == int(value) if key in ("installed", "enabled") else (current or "") == (value or "")
            if not same:
                row.set(key, value)
                changed = True
    if changed:
        doc.flags.ignore_permissions = True
        doc.flags.in_module_sync = True
        doc.save()
        after_change()
    return changed


def _can_switch() -> bool:
    from zatgo_core.services import app_authority

    return app_authority.is_system_context() or app_authority.can_switch()


def validate(doc: Any) -> None:
    """Module Settings controller rules: who may switch, the always-on modules, installed apps, dependencies."""
    before = doc.get_doc_before_save()
    was = {r.module: bool(r.enabled) for r in (before.get("modules") if before else [])} if before else {}
    rows = list(doc.get("modules") or [])
    changed = {r.module for r in rows if bool(r.enabled) != was.get(r.module, True)}
    if changed and not doc.flags.in_module_sync and not _can_switch():
        frappe.throw(_("Only a System Manager can switch modules on or off."), frappe.PermissionError)
    reg = _registry()
    for row in rows:
        if reg.get_module(row.module) is None:
            frappe.throw(_("{0} is not a ZatGo module.").format(row.module))
        if row.module in ALWAYS_ON and not row.enabled:
            frappe.throw(_("{0} is part of every ZatGo site and cannot be switched off.").format(row.module_label or row.module))
        if row.enabled and row.module in changed and not is_installed(row.module):
            frappe.throw(_("{0} needs the {1} app, which is not installed on this site.")
                         .format(row.module_label or row.module, reg.get_module(row.module).source_app))
    enabled = {r.module for r in rows if r.enabled} | ALWAYS_ON
    for module_id, needs in dependencies().items():
        if module_id not in enabled:
            continue
        missing = needs - enabled
        if missing and (module_id in changed or missing & changed):
            if module_id in changed:
                frappe.throw(_("{0} needs {1}. Switch that on first.").format(_labels({module_id}), _labels(missing).replace("\n", ", ")))
            frappe.throw(_("{0} is needed by {1}. Switch {1} off first.")
                         .format(_labels(missing & changed).replace("\n", ", "), _labels({module_id})))


def status() -> list[dict[str, Any]]:
    """Every module with its state, for clients and the hub (read-only)."""
    from zatgo_core.services.core import availability

    reg = _registry()
    rows = {r.module: r for r in _rows()}
    out = []
    for module in sorted(reg.modules(), key=lambda m: (m.order, m.id)):
        row = rows.get(module.id)
        state = availability.module(module.id)
        out.append({
            "module": module.id,
            "label": module.label,
            "enabled": state.enabled,
            "installed": state.installed,
            "licensed": state.licensed,
            "available": state.available,
            "reason": state.reason,
            "depends_on": sorted(dependencies().get(module.id, set())),
            "display_order": (row.display_order if row else None) or module.order,
            "icon": (row.icon if row else None) or module.icon,
            "workspace": row.workspace if row else None,
            "show_in_navigation": shows_in_navigation(module.id),
        })
    return out
