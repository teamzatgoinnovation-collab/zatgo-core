"""A visible, user-editable "Narration" on every transaction.

- Where ERPNext already has a free-text remark that flows into GL / ledger
  reports, that field *is* the narration: relabelled "Narration", its section
  shown expanded, and (Payment Entry / Journal Entry) no longer read-only
  until "Custom Remarks" is ticked -- services/narration.py ticks that flag
  for the user, so ERPNext's auto-text never overwrites what they wrote.
- Where there is none, `custom_narration` is added, in its own section at the
  top of the More Info tab (end of the form for Stock Reconciliation, which
  has no tabs).

Attachments need nothing: the form sidebar already allows them on all of
these doctypes.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

# doctype -> (native narration field, section to show expanded)
NATIVE_NARRATION = {
    "Payment Entry": ("remarks", "section_break_12"),
    "Journal Entry": ("remark", "addtional_info"),
    "Sales Invoice": ("remarks", "more_information"),
    "Purchase Invoice": ("remarks", "additional_info_section"),
    "POS Invoice": ("remarks", "more_info"),
    "Stock Entry": ("remarks", "more_info"),
    "Purchase Receipt": ("remarks", "additional_info_section"),
}

# ERPNext keeps these read-only until the custom flag is ticked.
READ_ONLY_UNTIL_FLAGGED = {"Payment Entry": "remarks", "Journal Entry": "remark"}

# doctype -> field the new Narration section goes after
NEW_NARRATION = {
    "Sales Order": "more_info",
    "Purchase Order": "more_info_tab",
    "Quotation": "more_info_tab",
    "Delivery Note": "more_info_tab",
    "Material Request": "more_info_tab",
    "Stock Reconciliation": "dimension_col_break",
}


def execute() -> None:
    fields: dict[str, list[dict]] = {}
    for doctype, after in NEW_NARRATION.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        fields[doctype] = [
            {
                "fieldname": "custom_narration_section",
                "label": "Narration",
                "fieldtype": "Section Break",
                "insert_after": after,
            },
            {
                "fieldname": "custom_narration",
                "label": "Narration",
                "fieldtype": "Small Text",
                "insert_after": "custom_narration_section",
                "no_copy": 1,
                "translatable": 0,
            },
        ]
    create_custom_fields(fields, update=True)

    for doctype, (fieldname, section) in NATIVE_NARRATION.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        meta = frappe.get_meta(doctype)
        if meta.has_field(fieldname):
            make_property_setter(
                doctype, fieldname, "label", "Narration", "Data", validate_fields_for_doctype=False
            )
        if meta.get_field(section):
            make_property_setter(
                doctype, section, "collapsible", 0, "Check", validate_fields_for_doctype=False
            )

    for doctype, fieldname in READ_ONLY_UNTIL_FLAGGED.items():
        if frappe.db.exists("DocType", doctype):
            make_property_setter(
                doctype, fieldname, "read_only_depends_on", "", "Code", validate_fields_for_doctype=False
            )

    frappe.db.commit()
