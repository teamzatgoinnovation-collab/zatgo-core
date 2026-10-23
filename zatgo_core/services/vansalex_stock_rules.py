"""Where a VanSaleX field user may move stock or write it off.

A field user is an enabled `ZG Van Sale Profile` that isn't an Admin one
(`vansalex_access.is_field_user`); admins and users without a van profile are
not limited by anything here (their ERPNext permissions still apply).

- Transfer (`inventory.transfer`, off until an admin turns it on): exactly one
  side is the user's own van, the other a warehouse of the same company that
  is ticked "VanSaleX Transfer Point". Van <-> van, and any other warehouse,
  are refused; with no transfer point ticked nothing can be transferred.
- Write-off (`inventory.adjust`, off until an admin turns it on): the user's
  own van only, a decrease only (a Material Issue -- stock never appears from
  nowhere), at most VanSaleX Settings -> Max Stock Write-off Qty per line.
- Nothing else: no Material Receipt, no manufacturing / repack / subcontract.
- Opening stock for a new item is an admin's job (`assert_opening_stock_allowed`).

One set of rules, two callers: the vansalex endpoints (`stock.transfer` /
`stock.adjust`, for a clear error before anything is built) and the Stock
Entry backstop (`assert_stock_entry`, any entry point: /api/resource, Desk).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt

TRANSFER_POINT_FIELD = "zg_vansalex_transfer_point"

MATERIAL_TRANSFER = "Material Transfer"
MATERIAL_ISSUE = "Material Issue"


def _deny(message: str) -> None:
    frappe.throw(message, frappe.PermissionError)


def own_van(user: str | None = None) -> str:
    """The user's van warehouse (profile, else the company default)."""
    from zatgo_core.services.vansalex_settings import resolve

    warehouse = resolve(user).get("warehouse") or ""
    if not warehouse:
        frappe.throw("No van warehouse assigned to your profile.", frappe.ValidationError)
    return warehouse


def is_transfer_point(warehouse: str | None, company: str | None) -> bool:
    """A ticked, enabled, leaf warehouse of [company]."""
    if not warehouse or not frappe.get_meta("Warehouse").has_field(TRANSFER_POINT_FIELD):
        return False
    row = frappe.db.get_value(
        "Warehouse",
        warehouse,
        ["company", "is_group", "disabled", TRANSFER_POINT_FIELD],
        as_dict=True,
    )
    return bool(
        row
        and cint(row.get(TRANSFER_POINT_FIELD))
        and not cint(row.is_group)
        and not cint(row.disabled)
        and row.company == company
    )


def writeoff_cap() -> float:
    from zatgo_core.services.vansalex_settings import _global_settings

    return flt(_global_settings().get("max_adjust_qty"))


def _check_transfer(source: str | None, target: str | None, van: str) -> None:
    source, target = (source or "").strip(), (target or "").strip()
    if not source or not target:
        _deny("A transfer needs a source and a target warehouse.")
    if source == target:
        frappe.throw("from_warehouse and to_warehouse must differ", frappe.ValidationError)
    if van not in (source, target):
        _deny("Access denied: a transfer must start or end at your van warehouse.")
    other = target if source == van else source
    company = frappe.db.get_value("Warehouse", van, "company")
    if not is_transfer_point(other, company):
        _deny(
            f"Access denied: {other} is not a VanSaleX transfer point. Ask your admin to "
            "tick 'VanSaleX Transfer Point' on the warehouse."
        )


def _check_writeoff(warehouse: str | None, delta: Any, van: str) -> None:
    if (warehouse or "").strip() != van:
        _deny("Access denied: you can only write off stock in your assigned warehouse.")
    qty = flt(delta)
    if qty > 0:
        _deny(
            "Access denied: drivers can only decrease van stock. Stock comes in by a transfer "
            "from a transfer point or a purchase."
        )
    cap = writeoff_cap()
    if cap > 0 and abs(qty) > cap:
        _deny(f"A write-off can't exceed {cap:g} per item for your account.")


def assert_transfer(source: str | None, target: str | None) -> None:
    """The session user (a field user) may move stock [source] -> [target]."""
    from zatgo_core.services.vansalex_access import require

    require("inventory.transfer")
    _check_transfer(source, target, own_van())


def assert_writeoff(warehouse: str | None, delta: Any) -> None:
    """The session user (a field user) may book [delta] (negative) in [warehouse]."""
    from zatgo_core.services.vansalex_access import require

    require("inventory.adjust")
    _check_writeoff(warehouse, delta, own_van())


def _purpose(doc) -> str:
    purpose = (doc.get("purpose") or "").strip()
    if not purpose and doc.get("stock_entry_type"):
        purpose = frappe.db.get_value("Stock Entry Type", doc.stock_entry_type, "purpose") or doc.stock_entry_type
    return purpose


def assert_stock_entry(doc) -> None:
    """Backstop for a field user's Stock Entry (insert, save and submit).
    Only a transfer or a write-off that follows the rules above; every other
    purpose (Material Receipt, Manufacture, Repack, ...) is refused."""
    from zatgo_core.services.vansalex_access import require

    require("inventory")
    purpose = _purpose(doc)
    rows = doc.get("items") or []
    if purpose == MATERIAL_TRANSFER:
        require("inventory.transfer")
        van = own_van()
        for row in rows:
            _check_transfer(row.get("s_warehouse"), row.get("t_warehouse"), van)
    elif purpose == MATERIAL_ISSUE:
        require("inventory.adjust")
        van = own_van()
        for row in rows:
            if row.get("t_warehouse"):
                _deny("Access denied: a write-off has no target warehouse.")
            _check_writeoff(row.get("s_warehouse"), -abs(flt(row.get("qty"))), van)
    else:
        _deny(
            f"Access denied: Stock Entry type '{purpose or doc.get('stock_entry_type')}' isn't "
            "available to VanSaleX field users (only transfers and write-offs, per your admin's settings)."
        )


def assert_opening_stock_allowed() -> None:
    """Opening stock (an item created with a quantity) is booked by an admin,
    not a field user. Raised before anything is written."""
    from zatgo_core.services.vansalex_access import is_field_user

    if is_field_user():
        _deny(
            "Access denied: opening stock can only be booked by an admin. Create the item "
            "without an opening quantity; stock reaches your van by a transfer or a purchase."
        )
