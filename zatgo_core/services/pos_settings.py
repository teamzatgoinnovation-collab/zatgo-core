"""What the ZatGo POS app is told about this site: `ZG POS Settings` as one flat dict.

Read by api/v1/pos_settings.py. Defaults are the ones in the DocType JSON, so a site that never saved the form
gets the same answer as one that saved it untouched."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt

SETTINGS = "ZG POS Settings"

# POS Type -> (pos_mode the POS app gets, industry that must be on for it). The industry gate stays the access rule.
POS_TYPES = {
    "Restaurant": ("restaurant", "restaurant"),
    "Supermarket": ("retail", "supermarket"),
}


def _chosen_type() -> str | None:
    """The stored POS Type, None while the form never set it (a Single reads blank, there is no default)."""
    try:
        value = frappe.get_cached_doc(SETTINGS).get("pos_type")
    except Exception:
        return None
    return value if value in POS_TYPES else None


def derived_type(enabled: set[str] | None = None) -> str | None:
    """What the industries say when no type was chosen: Restaurant wins when both are on."""
    if enabled is None:
        from zatgo_core.industries import gate

        enabled = gate.enabled_keys()
    for pos_type, (_mode, industry) in POS_TYPES.items():
        if industry in enabled:
            return pos_type
    return None


def pos_type(enabled: set[str] | None = None) -> str | None:
    return _chosen_type() or derived_type(enabled)


def pos_mode(enabled: set[str] | None = None) -> str | None:
    """"restaurant" | "retail" | None (nothing for the POS to do). A chosen type is authoritative but still needs
    its industry on; with no choice the industries decide, as before the setting existed."""
    if enabled is None:
        from zatgo_core.industries import gate

        enabled = gate.enabled_keys()
    chosen = _chosen_type()
    if chosen:
        mode, industry = POS_TYPES[chosen]
        return mode if industry in enabled else None
    derived = derived_type(enabled)
    return POS_TYPES[derived][0] if derived else None


def switch_industry_on(chosen: str) -> bool:
    """Make sure the industry of `chosen` is on. True if it had to be switched. Only turns on, never off: the other
    POS industry keeps its data and Desk entries, the type just stops selecting it."""
    industry = POS_TYPES[chosen][1]
    from zatgo_core.industries import gate
    from zatgo_core.industries.sync import ensure_rows

    if industry in gate.enabled_keys():
        return False
    settings = frappe.get_doc(gate.SETTINGS)
    ensure_rows(settings)
    for row in settings.enabled_industries:
        if row.industry == industry:
            row.enabled = 1
    # ZG System Settings' own validate checks the industry's requirements and who may switch.
    settings.save(ignore_permissions=True)
    return True


def effective() -> dict[str, Any]:
    doc = frappe.get_cached_doc(SETTINGS)
    allow_discounts = cint(doc.allow_discounts)
    return {
        "pos_type": pos_type(),
        "pos_mode": pos_mode(),
        "default_warehouse": doc.default_warehouse or None,
        "default_price_list": doc.default_price_list or None,
        "default_customer": doc.default_customer or None,
        "allow_discounts": allow_discounts,
        # No discounting means a 0 cap, whatever the stored percent says.
        "max_discount_percent": flt(doc.max_discount_percent) if allow_discounts else 0.0,
        "default_payment_mode": doc.default_payment_mode or None,
        "allow_split_payment": cint(doc.allow_split_payment),
        "receipt_header": doc.receipt_header or "",
        "receipt_footer": doc.receipt_footer or "",
        "show_tax_on_receipt": cint(doc.show_tax_on_receipt),
        "print_copies": max(cint(doc.print_copies), 1),
    }
