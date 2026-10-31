"""boot_session enrichment for Desk clients."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core import __version__
from zatgo_core.constants.settings import DOCTYPES
from zatgo_core.industries.gate import enabled_keys
from zatgo_core.services import app_catalog, app_page, app_sidebar, app_state, core_sidebar, settings_palette, ui_settings
from zatgo_core.services.sales_invoice_naming import get_session_user_series


def _desk_route(link_type: str, name: str) -> str:
    """Where Desk opens a Workspace / DocType / Page of this name (frappe.router.slug)."""
    return "/desk/" + app_page.workspace_slug(name)


def _app_entry_route(sidebar: dict) -> str | None:
    """The first thing an app's sidebar opens for this user: its Overview, else its first link."""
    for item in sidebar.get("items", []):
        if item.get("type") == "Link" and item.get("link_to") and item.get("link_type") in ("Workspace", "DocType", "Page"):
            return _desk_route(item["link_type"], item["link_to"])
    return None


_TILE_COLORS = ("#06B58B", "#3B82F6", "#8B5CF6", "#F59E0B", "#EF4444", "#14B8A6", "#EC4899", "#6366F1")
# A gear, drawn in a 54x54 tile, for "General Settings".
_GEAR = (
    "M27 17.5a2 2 0 0 1 2 2v1.3c.8.2 1.5.5 2.1.9l.9-.9a2 2 0 0 1 2.8 2.8l-.9.9c.4.6.7 1.3.9 2.1h1.3a2 2 0 0 1 "
    "0 4h-1.3c-.2.8-.5 1.5-.9 2.1l.9.9a2 2 0 0 1-2.8 2.8l-.9-.9c-.6.4-1.3.7-2.1.9v1.3a2 2 0 0 1-4 0v-1.3c-.8-.2-1.5-.5-2.1-.9l-.9.9"
    "a2 2 0 0 1-2.8-2.8l.9-.9c-.4-.6-.7-1.3-.9-2.1h-1.3a2 2 0 0 1 0-4h1.3c.2-.8.5-1.5.9-2.1l-.9-.9a2 2 0 0 1 2.8-2.8l.9.9"
    "c.6-.4 1.3-.7 2.1-.9v-1.3a2 2 0 0 1 2-2zm0 8a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z"
)


def _tile(label: str, general: bool = False, color: str | None = None) -> str:
    """The icon of a popup entry: a coloured rounded tile with the app's initials (a gear for General Settings),
    as a data URI -- no asset file per app, so a new app or industry needs nothing drawn. The colour is the app's
    accent (manifest `color`, the same one the Settings Map uses); an entry without one falls back to a hash of
    its label, so it keeps its colour on every site."""
    from urllib.parse import quote

    color = color if settings_palette.is_hex(color) else _TILE_COLORS[sum(ord(c) for c in label) % len(_TILE_COLORS)]
    if general:
        glyph = f'<path fill-rule="evenodd" d="{_GEAR}" fill="#fff"/>'
    else:
        words = [w for w in label.replace("ZatGo", "").split() if w] or [label]
        text = "".join(w[0] for w in words[:2]).upper()
        glyph = (
            f'<text x="27" y="35.5" font-family="Poppins,Arial,sans-serif" font-size="22" font-weight="600" '
            f'text-anchor="middle" fill="#fff">{text}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="54" height="54" viewBox="0 0 54 54">'
        f'<rect width="54" height="54" rx="15.4" fill="{color}"/>{glyph}</svg>'
    )
    return "data:image/svg+xml," + quote(svg)


def _accent(app: dict) -> str | None:
    """An app's accent; an industry (no manifest of its own) takes the Industries entry's."""
    return app.get("color") or (app_catalog.get("industries") or {}).get("color")


def _zatgo_folder_children(bootinfo: Any) -> None:
    """Fill the "ZatGo" folder of the Apps screen (/desk): its popup lists every ZatGo app that is switched on, plus
    "General Settings" (where apps are switched on and off), like the Frappe HR folder does.

    The children are not Desktop Icon rows (an icon's name is its label, and an app's own rail icon already
    has it); they are made here. An app is listed when its own sidebar (services/app_sidebar.py) has an item this
    user may open -- Frappe leaves a sidebar out of the boot otherwise -- and opens that sidebar's first link
    (Overview). The popup opens each child by its `link` (External icon = a plain URL)."""
    sidebars = bootinfo.get("workspace_sidebar_item") or {}
    folder = next((i for i in bootinfo.get("desktop_icons") or [] if i.get("label") == core_sidebar.NAME), None)
    if not folder or folder.get("icon_type") != "Folder":
        return
    children = []
    for app in app_page.apps():
        if not app_page.is_enabled(app):
            continue
        sidebar = sidebars.get(app_sidebar.sidebar_name(app).lower())
        route = _app_entry_route(sidebar) if sidebar else None
        if route:
            children.append((app["label"], app["icon"], route, _accent(app)))
    general = sidebars.get(core_sidebar.NAME.lower())
    general_target = None
    for item in (general or {}).get("items", []):
        if item.get("type") == "Link" and item.get("link_type") in ("Page", "DocType"):
            # The App Settings Hub where this site has it, else the first settings entry of the section.
            target = _desk_route(item["link_type"], item["link_to"])
            if item["link_to"] == core_sidebar.HUB_PAGE or not general_target:
                general_target = target
    if general_target:
        children.append((core_sidebar.GENERAL_LABEL, "setting", general_target, (app_catalog.get("core_settings") or {}).get("color")))
    by_label = {i.get("label"): i for i in bootinfo["desktop_icons"]}
    for idx, (label, icon, route, color) in enumerate(children):
        child = by_label.get(label)
        if child is None:
            child = frappe._dict(name=label, label=label, standard=0, bg_color=None, link_to=None, icon_image=None)
            bootinfo["desktop_icons"].append(child)
        # An app's own rail icon (same name, hidden) is reused for this user's boot only; the row is untouched.
        child.update(
            icon=icon or "list", icon_type="Link", link_type="External", link=route, parent_icon=folder["label"],
            app="zatgo_core", idx=idx, hidden=0, restrict_removal=1, icon_image=None,
            logo_url=_tile(label, general=label == core_sidebar.GENERAL_LABEL, color=color),
        )


def boot_session(bootinfo: Any) -> None:
    """Inject compact ZatGo Core boot payload for Desk / Vue clients."""
    try:
        system = {}
        if frappe.db.exists("DocType", DOCTYPES["SYSTEM_SETTINGS"]):
            if frappe.db.exists(DOCTYPES["SYSTEM_SETTINGS"], DOCTYPES["SYSTEM_SETTINGS"]):
                doc = frappe.get_cached_doc(
                    DOCTYPES["SYSTEM_SETTINGS"], DOCTYPES["SYSTEM_SETTINGS"]
                )
                brand = ui_settings.values()
                system = {
                    "brand_name": brand["brand_name"],
                    "theme": brand["theme"],
                    "default_company": doc.get("default_company"),
                    "maintenance_mode": doc.get("maintenance_mode"),
                    "autofill_payment_accounts": doc.get("autofill_payment_accounts"),
                    "enable_ifrs_reports": doc.get("enable_ifrs_reports"),
                }

        flags = []
        if frappe.db.exists("DocType", DOCTYPES["FEATURE_FLAG"]):
            flags = frappe.get_all(
                DOCTYPES["FEATURE_FLAG"],
                filters={"status": ("in", ["Enabled", "Beta", "Experimental", "Internal"])},
                fields=["flag_key", "status", "app_name"],
                limit_page_length=200,
            )

        bootinfo.zatgo_core = {
            "system": system,
            "feature_flags": flags,
            "version": __version__,
            # Old Desk URLs of the apps (/desk/zg-app/<app>, the names before "ZatGo ...") -> the app's Workspace.
            "app_routes": app_page.old_url_redirects(),
            # Settings DocType -> the sidebar of its app: opened directly (reload, bookmark) Frappe would pick
            # another sidebar listing the form (public/js/zg_sidebar_tabs.js).
            "settings_sidebars": app_sidebar.settings_sidebars(),
            # Apps with a switch that are on for this site (UI hint only; the server enforces,
            # services/app_gate.py).
            "apps": sorted(key for key, on in app_state.switches().items() if on),
            # Industries switched on for this site (UI hint only; the
            # server enforces, industries/gate.py).
            "industries": sorted(enabled_keys()),
            # This user's own invoice/return series per company, for the
            # Sales Invoice form (public/js/sales_invoice.js).
            "sales_invoice_naming": get_session_user_series(),
        }
        _zatgo_folder_children(bootinfo)
    except Exception:
        frappe.logger("zatgo_core").exception("boot_session enrichment failed")
