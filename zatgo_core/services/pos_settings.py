"""What the ZatGo POS app is told about this site: `ZG POS Settings` as one flat dict.

Read by api/v1/pos_settings.py. Defaults are the ones in the DocType JSON, so a site that never saved the form
gets the same answer as one that saved it untouched."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt

SETTINGS = "ZG POS Settings"

# POS Type -> (pos_mode the POS app gets, industry that must be on for it, vertical the POS app labels itself with).
# The industry gate stays the access rule. Cafe and General Retail are variants that run on the Restaurant and
# Supermarket engines; the types in COMING_SOON have no backend yet and cannot be chosen.
POS_TYPES = {
    "Restaurant": ("restaurant", "restaurant", "restaurant"),
    "Cafe": ("restaurant", "restaurant", "cafe"),
    "Supermarket": ("retail", "supermarket", "supermarket"),
    "General Retail": ("retail", "supermarket", "general"),
}
COMING_SOON = ("Pharmacy (coming soon)", "Electrical (coming soon)")
# The type that stands for an industry when nothing was chosen (Restaurant first: it wins when both are on).
DEFAULT_TYPE = {"restaurant": "Restaurant", "supermarket": "Supermarket"}


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
    for industry, pos_type in DEFAULT_TYPE.items():
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
        mode, industry, _vertical = POS_TYPES[chosen]
        return mode if industry in enabled else None
    derived = derived_type(enabled)
    return POS_TYPES[derived][0] if derived else None


def pos_vertical(enabled: set[str] | None = None) -> str | None:
    """What the POS app calls its business: restaurant | cafe | supermarket | general (None: nothing to do)."""
    chosen = pos_type(enabled)
    return POS_TYPES[chosen][2] if chosen and pos_mode(enabled) else None


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


OFFLINE_DEFAULTS = {"max_offline_hours": 72, "max_pending_sales": 500, "snapshot_refresh_minutes": 15}


def offline_policy(doc=None) -> dict[str, Any]:
    """What the POS may do without a connection (ZG POS Settings -> Offline). Off unless the site switched it on."""
    doc = doc or frappe.get_cached_doc(SETTINGS)
    return {
        "enabled": cint(doc.get("offline_enabled")),
        "max_offline_hours": cint(doc.get("max_offline_hours")) or OFFLINE_DEFAULTS["max_offline_hours"],
        "max_pending_sales": cint(doc.get("max_pending_sales")) or OFFLINE_DEFAULTS["max_pending_sales"],
        "snapshot_refresh_minutes": cint(doc.get("snapshot_refresh_minutes")) or OFFLINE_DEFAULTS["snapshot_refresh_minutes"],
        "allow_card_offline": cint(doc.get("allow_card_offline")),
    }


def _stored(doc, field: str, default):
    """The value the form shows. A Single nobody saved yet stores nothing and the document reads blank / 0, which is not the
    DocType's default (discounts on, 100%, split payment on ...): read tabSingles to tell 'never stored' from 'stored 0'."""
    if frappe.db.sql("select 1 from tabSingles where doctype = %s and field = %s", (SETTINGS, field)):
        return doc.get(field)
    return default


def discount_policy(doc=None) -> tuple[int, float]:
    """(allow_discounts, max_discount_percent) as ZG POS Settings stores them, with the DocType defaults when never saved."""
    doc = doc or frappe.get_cached_doc(SETTINGS)
    allow = cint(_stored(doc, "allow_discounts", 1))
    cap = flt(_stored(doc, "max_discount_percent", 100))
    # No discounting means a 0 cap, whatever the stored percent says.
    return allow, (cap if allow else 0.0)


def counter_policy(doc=None) -> dict[str, Any]:
    """Counter screen and invoice print defaults (ZG POS Settings), with the DocType defaults when never saved."""
    doc = doc or frappe.get_cached_doc(SETTINGS)
    paper = _stored(doc, "paper_size", "80mm")
    view = _stored(doc, "product_view", "Grid")
    qr = _stored(doc, "invoice_qr", "Phase 1")
    return {
        "paper_size": paper if paper in ("80mm", "A4") else "80mm",
        "product_view": "row" if view == "Row" else "grid",
        "allow_price_change": cint(_stored(doc, "allow_price_change", 0)),
        "invoice_qr": "off" if qr == "Off" else "phase1",
    }


def effective() -> dict[str, Any]:
    doc = frappe.get_cached_doc(SETTINGS)
    allow_discounts, max_discount_percent = discount_policy(doc)
    return {
        "pos_type": pos_type(),
        "pos_mode": pos_mode(),
        "pos_vertical": pos_vertical(),
        "default_warehouse": doc.default_warehouse or None,
        "default_price_list": doc.default_price_list or None,
        "default_customer": doc.default_customer or None,
        "allow_discounts": allow_discounts,
        "max_discount_percent": max_discount_percent,
        "default_payment_mode": doc.default_payment_mode or None,
        "allow_split_payment": cint(_stored(doc, "allow_split_payment", 1)),
        "receipt_header": doc.receipt_header or "",
        "receipt_footer": doc.receipt_footer or "",
        "show_tax_on_receipt": cint(_stored(doc, "show_tax_on_receipt", 1)),
        "print_copies": max(cint(doc.print_copies), 1),
        "offline": offline_policy(doc),
        "counter": counter_policy(doc),
    }
