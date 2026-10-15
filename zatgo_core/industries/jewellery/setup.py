"""Jewellery industry setup: custom fields on Item, shown while the industry is on."""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from zatgo_core.industries.sync import set_custom_fields_hidden

METALS = "\nGold\nSilver\nPlatinum"

ITEM_FIELDS = [
    {"fieldname": "zg_jewellery_section", "fieldtype": "Section Break", "label": "Jewellery", "insert_after": "description", "collapsible": 1},
    {"fieldname": "zg_jewellery_metal", "fieldtype": "Select", "label": "Metal", "options": METALS, "insert_after": "zg_jewellery_section"},
    {"fieldname": "zg_jewellery_purity", "fieldtype": "Data", "label": "Purity", "insert_after": "zg_jewellery_metal", "description": "e.g. 24K, 22K, 925"},
    {"fieldname": "zg_jewellery_gross_weight", "fieldtype": "Float", "label": "Gross Weight (g)", "insert_after": "zg_jewellery_purity", "precision": "3"},
    {"fieldname": "zg_jewellery_stone_weight", "fieldtype": "Float", "label": "Stone Weight (g)", "insert_after": "zg_jewellery_gross_weight", "precision": "3"},
    {"fieldname": "zg_jewellery_net_weight", "fieldtype": "Float", "label": "Net Weight (g)", "insert_after": "zg_jewellery_stone_weight", "precision": "3", "description": "Metal weight; set when empty from gross minus stone."},
    {"fieldname": "zg_jewellery_making_charge", "fieldtype": "Currency", "label": "Making Charge per Gram", "insert_after": "zg_jewellery_net_weight"},
    {"fieldname": "zg_jewellery_wastage", "fieldtype": "Percent", "label": "Wastage %", "insert_after": "zg_jewellery_making_charge"},
    {"fieldname": "zg_jewellery_hallmark", "fieldtype": "Data", "label": "Hallmark ID", "insert_after": "zg_jewellery_wastage"},
]
FIELD_NAMES = {"Item": [f["fieldname"] for f in ITEM_FIELDS]}


def enable() -> None:
    create_custom_fields({"Item": ITEM_FIELDS}, update=True)
    set_custom_fields_hidden(FIELD_NAMES, 0)


def disable() -> None:
    set_custom_fields_hidden(FIELD_NAMES, 1)
