"""Print-count tracking for Original/Duplicate Copy labeling.

Frappe has no built-in per-document print counter, and there is no way
for a server to observe that a physical page actually came out of a
printer -- `trigger_print` (the query param Frappe's own print view uses
to auto-fire the browser's print dialog, see frappe/www/printview.py) is
the closest reliable, purpose-built signal Frappe provides for "the user
invoked Print", as opposed to just opening the preview dialog to look at
it. See zatgo_core.services.print_tracking for the read/increment logic
that uses this field.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
    if not frappe.db.exists("DocType", "Sales Invoice"):
        return
    create_custom_fields(
        {
            "Sales Invoice": [
                {
                    "fieldname": "custom_print_count",
                    "label": "Print Count",
                    "fieldtype": "Int",
                    "default": "0",
                    "read_only": 1,
                    "hidden": 1,
                    "no_copy": 1,
                    "print_hide": 1,
                    "insert_after": "letter_head",
                    "translatable": 0,
                },
            ],
        },
        update=True,
    )
    frappe.db.commit()
