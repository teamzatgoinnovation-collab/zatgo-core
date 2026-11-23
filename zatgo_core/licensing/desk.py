"""Desk navigation follows the licence: workspaces, sidebars, rail icons and pages that only unlicensed features
use are left out of the boot payload (docs/licensing.md, Phase 4).

Per request and nothing stored: no Workspace, Desktop Icon or Page record is changed, so a new licence shows
everything again at the next page load. This is navigation only -- the server-side refusal is licensing/gate.py,
and reading existing records stays allowed (decision D6), so a direct URL still opens a record read-only.

An entry is hidden when some live feature lists it and no licensed feature (the foundation included) does --
shared workspaces such as "Invoicing" stay while any feature using them is licensed, and anything the registry
does not describe is never touched.
"""

from __future__ import annotations

from typing import Any

from zatgo_core.licensing import entitlement as ent
from zatgo_core.licensing import registry


def hidden(entitlement: ent.Entitlement) -> dict[str, set[str]]:
    live = [f for f in registry.features() if not f.retired]
    workspaces = {w for f in live for w in f.workspaces} - set(entitlement.workspaces)
    pages = {p for f in live for p in f.pages} - set(entitlement.pages)
    return {"workspaces": workspaces, "pages": pages}


def _name(entry: Any) -> str | None:
    if isinstance(entry, dict):
        return entry.get("name") or entry.get("label") or entry.get("title")
    return getattr(entry, "name", None) or getattr(entry, "label", None)


def filter_boot(bootinfo: Any) -> None:
    """boot_session: drop unlicensed Desk entries. Does nothing while no licence is enforced."""
    entitlement = ent.active()
    if entitlement is None:
        return
    hide = hidden(entitlement)
    ws, pages = hide["workspaces"], hide["pages"]
    ws_lower = {w.lower() for w in ws}

    workspaces = bootinfo.get("workspaces")
    if isinstance(workspaces, dict) and isinstance(workspaces.get("pages"), list):
        workspaces["pages"] = [p for p in workspaces["pages"] if _name(p) not in ws]

    sidebars = bootinfo.get("workspace_sidebar_item")
    if isinstance(sidebars, dict):
        for key in [k for k in sidebars if str(k).lower() in ws_lower]:
            sidebars.pop(key, None)

    icons = bootinfo.get("desktop_icons")
    if isinstance(icons, list):
        bootinfo["desktop_icons"] = [
            i for i in icons
            if not (isinstance(i, dict) and (i.get("label") in ws or i.get("link_to") in ws))
        ]

    page_info = bootinfo.get("page_info")
    if isinstance(page_info, dict):
        for key in [k for k in page_info if k in pages]:
            page_info.pop(key, None)

    bootinfo["zatgo_licence"] = {"enforcing": True, "hidden_workspaces": sorted(ws), "hidden_pages": sorted(pages)}
