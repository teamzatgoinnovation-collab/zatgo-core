"""Apply a site's industry selection: settings rows, roles, custom fields and
Desk entries (workspace, sidebar, desktop icon).

Run by ZG System Settings on save and by after_migrate. Switching an
industry off removes its Desk entries and hides its custom fields; it never
deletes data, DocTypes, roles or custom fields.
"""

from __future__ import annotations

import importlib
import json

import frappe

from zatgo_core.industries import registry
from zatgo_core.industries.gate import enabled_keys

MODULE = "ZatGo Core"



# -- settings rows -----------------------------------------------------------------


def ensure_rows(settings) -> None:
    """One row per registered industry, in registry order; keeps the
    `enabled` flags already stored, drops unknown/duplicate keys."""
    current: dict[str, bool] = {}
    for row in settings.get("enabled_industries") or []:
        if row.industry in registry.INDUSTRIES and row.industry not in current:
            current[row.industry] = bool(row.enabled)
    settings.set("enabled_industries", [])
    for key, ind in registry.INDUSTRIES.items():
        settings.append(
            "enabled_industries",
            {
                "industry": key,
                "industry_label": ind.label,
                "availability": "Ready" if ind.implemented else "Coming soon",
                "description": ind.description,
                "enabled": 1 if current.get(key) and ind.implemented else 0,
            },
        )


def industries_changed(before, after) -> bool:
    def flags(doc):
        return {r.industry for r in (doc.get("enabled_industries") or []) if r.enabled}

    return flags(before) != flags(after)


# -- sync ----------------------------------------------------------------------------


def sync_industries() -> None:
    """Set up what is switched on, take the Desk entries of what is off."""
    on = enabled_keys()
    for key, ind in registry.INDUSTRIES.items():
        if not ind.implemented:
            continue
        try:
            if key in on:
                enable(key)
            else:
                disable(key)
        except Exception:
            frappe.log_error(title=f"zatgo_core industry sync: {key}")
    frappe.clear_cache()


def _hook(key: str):
    try:
        return importlib.import_module(f"zatgo_core.industries.{key}.setup")
    except ModuleNotFoundError:
        return None


def enable(key: str) -> None:
    ind = registry.INDUSTRIES[key]
    for role in ind.roles:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True
            )
    mod = _hook(key)
    if mod and hasattr(mod, "enable"):
        mod.enable()
    _ensure_desk_entries(ind)


def disable(key: str) -> None:
    ind = registry.INDUSTRIES[key]
    mod = _hook(key)
    if mod and hasattr(mod, "disable"):
        mod.disable()
    _remove_desk_entries(ind)


# -- Desk entries --------------------------------------------------------------------


def _existing_links(ind: registry.Industry) -> list[tuple[str, str]]:
    return [(label, dt) for label, dt in ind.workspace_links if frappe.db.exists("DocType", dt)]


def _ensure_desk_entries(ind: registry.Industry) -> None:
    links = _existing_links(ind)
    name = ind.workspace
    content = [
        {"id": f"{ind.key}_hdr", "type": "header", "data": {"text": f"<span class=\"h4\"><b>{ind.label}</b></span>", "col": 12}}
    ] + [
        {"id": f"{ind.key}_s{i}", "type": "shortcut", "data": {"shortcut_name": label, "col": 3}}
        for i, (label, _dt) in enumerate(links)
    ]
    if not frappe.db.exists("Workspace", name):
        ws = frappe.get_doc(
            {
                "doctype": "Workspace",
                "name": name,
                "label": name,
                "title": name,
                # No module/app: Frappe's migrate deletes public workspaces
                # that have both but no file on disk ("orphans").
                "public": 1,
                "icon": ind.icon,
                "content": json.dumps(content),
                "roles": [{"role": r} for r in (*ind.roles, "System Manager")] if ind.roles else [],
                "shortcuts": [{"label": label, "type": "DocType", "link_to": dt, "doc_view": "List"} for label, dt in links],
            }
        )
        ws.flags.ignore_links = True
        ws.insert(ignore_permissions=True)
    if not frappe.db.exists("Workspace Sidebar", name):
        sb = frappe.get_doc(
            {
                "doctype": "Workspace Sidebar",
                "name": name,
                "title": name,
                "header_icon": ind.icon,
                "module": MODULE,
                "app": "zatgo_core",
                "standard": 0,
                "items": [
                    {"label": label, "link_type": "DocType", "link_to": dt, "type": "Link", "icon": "list"}
                    for label, dt in links
                ],
            }
        )
        sb.flags.ignore_links = True
        sb.insert(ignore_permissions=True)
    if not frappe.db.exists("Desktop Icon", name):
        icon = frappe.get_doc(
            {
                "doctype": "Desktop Icon",
                "label": name,
                "app": "zatgo_core",
                "icon_type": "Link",
                "link_type": "Workspace Sidebar",
                "link_to": name,
                "icon": ind.icon,
                "standard": 0,
                "hidden": 0,
            }
        )
        icon.flags.ignore_links = True
        icon.insert(ignore_permissions=True)


def _remove_desk_entries(ind: registry.Industry) -> None:
    name = ind.workspace
    for doctype in ("Desktop Icon", "Workspace Sidebar", "Workspace"):
        if frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)


def set_custom_fields_hidden(fields: dict[str, list[str]], hidden: int) -> None:
    """Hide / show custom fields {doctype: [fieldname, ...]} (data is kept)."""
    for dt, names in fields.items():
        for fn in names:
            cf = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fn}, "name")
            if cf:
                frappe.db.set_value("Custom Field", cf, "hidden", hidden, update_modified=False)
