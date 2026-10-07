"""Seed VanSaleX Settings → Modules & Features rows (services/vansalex_access.py).

Runs on every migrate. Only ADDS rows for catalog keys the site doesn't have
yet, using the key's catalog default — never changes an existing row's
on/off, so an admin's switch survives upgrades (rows are re-ordered to the
app's order and their labels refreshed, nothing else). Existing functionality
defaults on (a site upgraded to this keeps everything it had) — including
keys split out of an existing one (Activities, Documents, My Performance);
genuinely new functionality defaults off.
"""

from __future__ import annotations

import frappe

from zatgo_core.services.vansalex_access import APP_LOCATION, CATALOG, ROW_KEYS, SETTINGS_DOCTYPE


def ensure_vansalex_access() -> None:
    if not frappe.db.exists("DocType", "VanSaleX Access"):
        return
    doc = frappe.get_single(SETTINGS_DOCTYPE)
    have = {r.access_key for r in doc.get("access") or []}
    missing = [k for k in ROW_KEYS if k not in have]
    for key in missing:
        kind, label, parent, default, _derived = CATALOG[key]
        doc.append("access", {"access_key": key, "kind": kind, "label": label, "enabled": default})
    # Rows follow the catalog's order (the app's order) — only their position
    # moves; nobody's on/off choice is touched. Labels / app locations are
    # refreshed by the controller's validate().
    order = {k: i for i, k in enumerate(ROW_KEYS)}
    rows = sorted(doc.get("access") or [], key=lambda r: order.get(r.access_key, len(order)))
    stale = any(
        r.label != CATALOG[r.access_key][1] or (r.get("app_location") or "") != APP_LOCATION.get(r.access_key, "")
        for r in rows
        if r.access_key in CATALOG
    )
    reordered = [r.access_key for r in rows] != [r.access_key for r in doc.get("access") or []]
    if not (missing or stale or reordered):
        return
    for i, r in enumerate(rows, start=1):
        r.idx = i
    doc.set("access", rows)
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.save()
