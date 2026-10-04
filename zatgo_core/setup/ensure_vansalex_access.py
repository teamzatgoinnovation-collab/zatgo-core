"""Seed VanSaleX Settings → Modules & Features rows (services/vansalex_access.py).

Runs on every migrate. Only ADDS rows for catalog keys the site doesn't have
yet, using the key's catalog default — never changes an existing row, so an
admin's switch survives upgrades. Existing functionality defaults on (a site
upgraded to this keeps everything it had); keys added later default off.
"""

from __future__ import annotations

import frappe

from zatgo_core.services.vansalex_access import CATALOG, ROW_KEYS, SETTINGS_DOCTYPE


def ensure_vansalex_access() -> None:
    if not frappe.db.exists("DocType", "VanSaleX Access"):
        return
    doc = frappe.get_single(SETTINGS_DOCTYPE)
    have = {r.access_key for r in doc.get("access") or []}
    missing = [k for k in ROW_KEYS if k not in have]
    if not missing:
        return
    for key in missing:
        kind, label, parent, default, _derived = CATALOG[key]
        doc.append(
            "access",
            {"access_key": key, "label": label, "kind": kind, "parent_module": parent or "", "enabled": default},
        )
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.save()
