"""Map legacy delivery stop statuses to the 2A workflow."""

from __future__ import annotations

import frappe

_MAP = {
    "Pending": "Assigned",
    "En Route": "Out For Delivery",
    "Arrived": "Out For Delivery",
}


def execute() -> None:
    if not frappe.db.exists("DocType", "ZG Delivery Stop"):
        return
    for old, new in _MAP.items():
        frappe.db.sql(
            """
            UPDATE `tabZG Delivery Stop`
            SET status = %s
            WHERE status = %s
            """,
            (new, old),
        )
    frappe.db.commit()
