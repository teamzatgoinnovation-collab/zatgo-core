"""Original/Duplicate Copy labeling for print formats.

No web application can observe that ink actually left a printer -- the
closest thing Frappe itself provides is `trigger_print`, the query
parameter its own print view uses to auto-fire the browser's print
dialog (frappe/www/printview.py) rather than just render a preview a
user is looking at without printing. That's the signal this module
treats as "a real print happened": present and truthy only when the
Print action (not the preview-open) is what produced this render.

Exposed to Jinja print formats via hooks.py's `jinja.methods` -- call it
once per print format render, outside any per-page/per-copy loop, e.g.
`{% set copy_label = get_copy_label(doc) %}`. The label itself always
reflects the CURRENT persisted count (so a preview shows what printing
right now would produce); only a genuine trigger_print request mutates
that count, and does so via a single atomic UPDATE (not read-modify-
write) since concurrent renders of the same invoice are possible.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

ORIGINAL_LABEL = "ORIGINAL COPY"
DUPLICATE_LABEL = "DUPLICATE COPY"


def get_copy_label(doc) -> str:
    if not doc or not doc.get("name") or not frappe.db.exists(doc.doctype, doc.name):
        return ORIGINAL_LABEL

    current_count = frappe.db.get_value(doc.doctype, doc.name, "custom_print_count") or 0
    label = DUPLICATE_LABEL if current_count > 0 else ORIGINAL_LABEL

    if cint(frappe.form_dict.get("trigger_print")):
        frappe.db.sql(
            f"update `tab{doc.doctype}` set custom_print_count = coalesce(custom_print_count, 0) + 1 where name = %s",
            (doc.name,),
        )

    return label
