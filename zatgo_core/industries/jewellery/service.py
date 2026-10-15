"""Jewellery pricing: metal value + wastage + making charge, from the latest
ZG Metal Rate. Sale/purchase/return use the standard invoices."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate


def latest_rate(metal: str, purity: str, on_date=None) -> float:
    row = frappe.db.get_value(
        "ZG Metal Rate",
        {"metal": metal, "purity": purity, "rate_date": ("<=", getdate(on_date))},
        "rate_per_gram",
        order_by="rate_date desc, creation desc",
    )
    if not row:
        frappe.throw(_("No {0} {1} rate on or before {2}").format(metal, purity, getdate(on_date)))
    return flt(row)


def price(item_code: str, on_date=None) -> dict:
    """Price breakdown of a jewellery Item."""
    frappe.has_permission("Item", "read", item_code, throw=True)
    it = frappe.db.get_value(
        "Item",
        item_code,
        [
            "zg_jewellery_metal",
            "zg_jewellery_purity",
            "zg_jewellery_gross_weight",
            "zg_jewellery_stone_weight",
            "zg_jewellery_net_weight",
            "zg_jewellery_making_charge",
            "zg_jewellery_wastage",
        ],
        as_dict=True,
    )
    if not it or not it.zg_jewellery_metal or not it.zg_jewellery_purity:
        frappe.throw(_("Item {0} has no jewellery metal / purity").format(item_code))
    net = flt(it.zg_jewellery_net_weight) or max(flt(it.zg_jewellery_gross_weight) - flt(it.zg_jewellery_stone_weight), 0)
    if net <= 0:
        frappe.throw(_("Item {0} has no weight").format(item_code))
    rate = latest_rate(it.zg_jewellery_metal, it.zg_jewellery_purity, on_date)
    metal_value = net * rate
    wastage = metal_value * flt(it.zg_jewellery_wastage) / 100
    making = net * flt(it.zg_jewellery_making_charge)
    return {
        "item_code": item_code,
        "net_weight": net,
        "rate_per_gram": rate,
        "metal_value": round(metal_value, 2),
        "wastage": round(wastage, 2),
        "making_charge": round(making, 2),
        "total": round(metal_value + wastage + making, 2),
    }
