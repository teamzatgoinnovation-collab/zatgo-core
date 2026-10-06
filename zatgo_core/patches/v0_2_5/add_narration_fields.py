"""Narration + Attachment on the main tab of every transaction.

Each doctype gets a "Narration" section right after its main table (entries
/ items / Payment Entry's reference no. and date), holding:

- the narration: ERPNext's own remark field where one exists and flows into
  GL / ledger reports (relabelled "Narration" and moved here), else a new
  `custom_narration`. On Payment Entry / Journal Entry it is no longer
  read-only until "Custom Remarks" is ticked -- services/narration.py ticks
  that flag for the user, so ERPNext's auto-text never overwrites it;
- `custom_attachment` (Attach): a file can be added before the first save,
  when the form sidebar's Attachments isn't shown yet. Frappe links it to the
  document on save (core attach_files_to_document); more files go through the
  sidebar as usual.

The block is placed with a `field_order` property setter (what Customize
Form saves), recomputed from the site's current layout so other
customisations are kept. Runs on every migrate (setup/ensure_custom_fields.py),
so it is also what cleans up the first version (narration on the More Info
tab, expanded "Additional Info" sections).
"""

from __future__ import annotations

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

# doctype -> field the Narration section goes after (its section's end)
ANCHOR = {
    "Payment Entry": "reference_date",
    "Journal Entry": "accounts",
    "Sales Invoice": "items",
    "Purchase Invoice": "items",
    "POS Invoice": "items",
    "Stock Entry": "items",
    "Purchase Receipt": "items",
    "Sales Order": "items",
    "Purchase Order": "items",
    "Quotation": "items",
    "Delivery Note": "items",
    "Material Request": "items",
    "Stock Reconciliation": "items",
}

# doctypes whose own remark field is the narration
NATIVE_NARRATION = {
    "Payment Entry": "remarks",
    "Journal Entry": "remark",
    "Sales Invoice": "remarks",
    "Purchase Invoice": "remarks",
    "POS Invoice": "remarks",
    "Stock Entry": "remarks",
    "Purchase Receipt": "remarks",
}
NEW_NARRATION = [dt for dt in ANCHOR if dt not in NATIVE_NARRATION]

# ERPNext keeps these read-only until the custom flag is ticked.
READ_ONLY_UNTIL_FLAGGED = {"Payment Entry": "remarks", "Journal Entry": "remark"}

# First version expanded these sections to show the narration in place.
_OLD_EXPANDED_SECTIONS = {
    "Payment Entry": "section_break_12",
    "Journal Entry": "addtional_info",
    "Sales Invoice": "more_information",
    "Purchase Invoice": "additional_info_section",
    "POS Invoice": "more_info",
    "Stock Entry": "more_info",
    "Purchase Receipt": "additional_info_section",
}


def narration_field(doctype: str) -> str:
    return NATIVE_NARRATION.get(doctype, "custom_narration")


def execute() -> None:
    doctypes = [dt for dt in ANCHOR if frappe.db.exists("DocType", dt)]

    fields: dict[str, list[dict]] = {}
    for doctype in doctypes:
        rows = [
            {
                "fieldname": "custom_narration_section",
                "label": "Narration",
                "fieldtype": "Section Break",
                "insert_after": ANCHOR[doctype],
            }
        ]
        last = "custom_narration_section"
        if doctype not in NATIVE_NARRATION:
            rows.append(
                {
                    "fieldname": "custom_narration",
                    "label": "Narration",
                    "fieldtype": "Small Text",
                    "insert_after": last,
                    "no_copy": 1,
                    "translatable": 0,
                }
            )
            last = "custom_narration"
        rows += [
            {
                "fieldname": "custom_narration_cb",
                "fieldtype": "Column Break",
                "insert_after": last,
            },
            {
                "fieldname": "custom_attachment",
                "label": "Attachment",
                "fieldtype": "Attach",
                "insert_after": "custom_narration_cb",
                "no_copy": 1,
                "allow_on_submit": 1,
                "description": "Receipt, voucher scan, etc. Add more files from the Attachments panel after saving.",
            },
        ]
        fields[doctype] = rows
    create_custom_fields(fields, update=True)

    for doctype in doctypes:
        frappe.clear_cache(doctype=doctype)
        if doctype in NATIVE_NARRATION:
            make_property_setter(
                doctype, NATIVE_NARRATION[doctype], "label", "Narration", "Data",
                validate_fields_for_doctype=False,
            )
        _place_narration_block(doctype)
        if doctype in READ_ONLY_UNTIL_FLAGGED:
            make_property_setter(
                doctype, READ_ONLY_UNTIL_FLAGGED[doctype], "read_only_depends_on", "", "Code",
                validate_fields_for_doctype=False,
            )
        old_section = _OLD_EXPANDED_SECTIONS.get(doctype)
        if old_section:
            frappe.db.delete(
                "Property Setter",
                {"doc_type": doctype, "field_name": old_section, "property": "collapsible"},
            )
        frappe.clear_cache(doctype=doctype)

    frappe.db.commit()


def _place_narration_block(doctype: str) -> None:
    """Section + narration + attachment right after the anchor's section,
    and never past a tab boundary; every other field stays where the site's
    current layout has it (explicit order: Frappe's insert_after for a section
    break can land it on the next tab when the anchor ends a tab)."""
    meta = frappe.get_meta(doctype, cached=False)
    block = ["custom_narration_section", narration_field(doctype), "custom_narration_cb", "custom_attachment"]
    order = [df.fieldname for df in meta.fields]
    if any(f not in order for f in block) or ANCHOR[doctype] not in order:
        return
    order = [f for f in order if f not in block]
    i = order.index(ANCHOR[doctype]) + 1
    while i < len(order) and meta.get_field(order[i]).fieldtype not in ("Section Break", "Tab Break"):
        i += 1
    order[i:i] = block
    make_property_setter(
        doctype, None, "field_order", json.dumps(order), "Data", for_doctype=True,
        validate_fields_for_doctype=False,
    )
