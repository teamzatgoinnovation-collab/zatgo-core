"""Who may switch ZatGo apps (and industries) on or off.

The App Settings Hub only lets a System Manager do it, but the switches are plain fields of ZatGo System
Settings -- and that DocType is also writable by ZatGo Application Admin and ZatGo Company Admin (Desk form, REST
API). A UI-only rule is not security, so the DocType controller asks here on every save: changing an app's
switch or the Industries table is a System Manager's call, whatever route the save took.

Install, migrate and patches (`frappe.flags`) are system code, not a user, and pass; so does Administrator.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from zatgo_core.services import app_catalog, app_state


def can_switch(user: str | None = None) -> bool:
    user = user or frappe.session.user
    return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def is_system_context() -> bool:
    flags = frappe.flags
    return bool(flags.in_install or flags.in_migrate or flags.in_patch or flags.in_import)


def changed_switches(before: Any | None, after: Any) -> set[str]:
    """Keys of the apps whose switch differs between two ZatGo System Settings documents. With no `before`
    (first save) every switchable app counts as changed."""
    if before is None:
        return {a["key"] for a in app_catalog.catalog() if a["switch_field"]}
    old, new = app_state.switches_of(before), app_state.switches_of(after)
    return {key for key in new if new[key] != old.get(key)}


def assert_can_switch(before: Any | None, after: Any) -> None:
    """Throw unless the save changes no app switch and no industry, or the user may switch. Also refuses a
    state where an app is on while an app it `requires` is off (a state that was already broken is not
    held against an unrelated save)."""
    if before is None or is_system_context():
        return
    from zatgo_core.industries.sync import industries_changed

    changed = changed_switches(before, after)
    industries = industries_changed(before, after)
    if not (changed or industries):
        return
    if not can_switch():
        frappe.throw(
            _("Only a System Manager can switch apps or industries on or off."),
            frappe.PermissionError,
        )
    if changed:
        old = set(app_catalog.dependency_problems(app_state.switches_of(before)))
        new = [p for p in app_catalog.dependency_problems(app_state.switches_of(after)) if p not in old]
        if new:
            frappe.throw(_("Cannot save: {0}.").format("; ".join(new)))
    _refuse_unlicensed(before, after, changed, industries)


def _refuse_unlicensed(before: Any, after: Any, changed: set[str], industries: bool) -> None:
    """Switching ON an app or industry the site's licence does not include is refused (licensing/gate.py;
    never while no licence is enforced). Switching off, and leaving an existing state alone, always works."""
    from zatgo_core.licensing.gate import app_licensed, industry_licensed

    old_on, new_on = app_state.switches_of(before), app_state.switches_of(after)
    apps = sorted(k for k in changed if new_on.get(k) and not old_on.get(k) and not app_licensed(k))
    names = [(app_catalog.get(k) or {"label": k})["label"] for k in apps]
    if industries:
        def on(doc):
            return {r.industry for r in (doc.get("enabled_industries") or []) if r.enabled}

        names += sorted(k for k in on(after) - on(before) if not industry_licensed(k))
    if names:
        frappe.throw(
            _("Your ZatGo licence does not include: {0}.").format(", ".join(names)),
            frappe.PermissionError,
            title=_("Not licensed"),
        )
