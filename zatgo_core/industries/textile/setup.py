"""Textile industry setup: Item fields for fabric, shown while the industry is on.

Brand, colour and size reuse ERPNext's own Item Brand and variant attributes
(Item Attribute "Color" / "Size"), so variants, barcodes, purchase, sale and
stock tracking stay standard; these fields only add what ERPNext has no
place for. Roll length is kept in metres, width in centimetres."""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from zatgo_core.industries.sync import set_custom_fields_hidden

ITEM_FIELDS = [
    {"fieldname": "zg_textile_section", "fieldtype": "Section Break", "label": "Textile", "insert_after": "description", "collapsible": 1},
    {"fieldname": "zg_textile_fabric", "fieldtype": "Data", "label": "Fabric", "insert_after": "zg_textile_section", "description": "e.g. Cotton, Linen, Silk"},
    {"fieldname": "zg_textile_pattern", "fieldtype": "Data", "label": "Pattern", "insert_after": "zg_textile_fabric"},
    {"fieldname": "zg_textile_design", "fieldtype": "Data", "label": "Design No.", "insert_after": "zg_textile_pattern"},
    {"fieldname": "zg_textile_gsm", "fieldtype": "Float", "label": "GSM", "insert_after": "zg_textile_design", "description": "Weight, grams per square metre"},
    {"fieldname": "zg_textile_cb", "fieldtype": "Column Break", "insert_after": "zg_textile_gsm"},
    {"fieldname": "zg_textile_is_roll", "fieldtype": "Check", "label": "Sold by Roll", "insert_after": "zg_textile_cb"},
    {"fieldname": "zg_textile_roll_length", "fieldtype": "Float", "label": "Roll Length (m)", "insert_after": "zg_textile_is_roll", "depends_on": "zg_textile_is_roll", "precision": "2"},
    {"fieldname": "zg_textile_width", "fieldtype": "Float", "label": "Width (cm)", "insert_after": "zg_textile_roll_length", "precision": "1"},
]
FIELD_NAMES = {"Item": [f["fieldname"] for f in ITEM_FIELDS]}


def enable() -> None:
    create_custom_fields({"Item": ITEM_FIELDS}, update=True)
    set_custom_fields_hidden(FIELD_NAMES, 0)


def disable() -> None:
    set_custom_fields_hidden(FIELD_NAMES, 1)
