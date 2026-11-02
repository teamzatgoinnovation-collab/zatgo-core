"""Create the default Duplicate Prevention rules (services/duplicate/defaults.py). Only missing rules are created
and only from fields the DocType has; an administrator's edits are never overwritten."""

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "ZG Duplicate Rule"):
        return
    from zatgo_core.services.duplicate import config
    from zatgo_core.services.duplicate.defaults import seed_defaults

    seed_defaults()
    config.clear_cache()
