"""Resto POS was ungated before the Restaurant industry existed: keep it on
for sites that already use it (any ZG Table / ZG Order); new sites start with
every industry off."""

from __future__ import annotations

import frappe

from zatgo_core.industries.sync import ensure_rows


def execute() -> None:
    if not any(frappe.db.table_exists(dt) and frappe.db.count(dt) for dt in ("ZG Table", "ZG Order")):
        return
    settings = frappe.get_doc("ZG System Settings")
    ensure_rows(settings)
    for row in settings.enabled_industries:
        if row.industry == "restaurant":
            row.enabled = 1
    settings.flags.ignore_permissions = True
    settings.save()
    frappe.db.commit()
