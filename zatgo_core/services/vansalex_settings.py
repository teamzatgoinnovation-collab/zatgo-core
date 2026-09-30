"""Effective VanSaleX settings for a user.

Company-wide defaults live in the `VanSaleX Settings` single; a user's
`ZG Van Sale Profile` may override them (blank / "Inherit" = use the
default). Account and warehouse defaults come from ERPNext's own records
first and zatgo_core's second:

- warehouse:    Profile.warehouse → ZG Company Settings.default_warehouse
                → ERPNext Stock Settings.default_warehouse
- cash account: Profile.cash_account → ERPNext Mode of Payment "Cash"
                default account for the company → ZG Company Settings
                .default_cash_account

This is the single source for both the mobile app (served through
`vansalex.me.context`) and server-side validation of sales, so the app
can't be configured into something the server then rejects.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt

SETTINGS_DOCTYPE = "VanSaleX Settings"
PROFILE_DOCTYPE = "ZG Van Sale Profile"
CASH_MODE_OF_PAYMENT = "Cash"
PAYMENT_TYPES = ("Cash", "Credit")

_DEFAULTS: dict[str, Any] = {
    "default_payment_type": "Cash",
    "allow_credit_sales": 1,
    "show_payment_type_on_invoice": 1,
    "show_warehouse_on_invoice": 1,
    "allow_warehouse_change": 0,
    "allow_orders": 1,
    "max_discount_percent": 100,
    "restrict_collections_to_route": 1,
}


def _global_settings() -> dict[str, Any]:
    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        return dict(_DEFAULTS)
    doc = frappe.get_cached_doc(SETTINGS_DOCTYPE)
    out = dict(_DEFAULTS)
    for key in _DEFAULTS:
        value = doc.get(key)
        if value not in (None, ""):
            out[key] = value
    return out


def _profile_row(user: str) -> dict[str, Any]:
    if not frappe.db.exists("DocType", PROFILE_DOCTYPE):
        return {}
    name = frappe.db.get_value(PROFILE_DOCTYPE, {"user": user, "enabled": 1}, "name")
    return frappe.get_doc(PROFILE_DOCTYPE, name).as_dict() if name else {}


def _override(profile: dict[str, Any], key: str, default: Any) -> int:
    """Profile Select "Inherit"/"Yes"/"No" (or blank) over a global Check."""
    value = (profile.get(key) or "").strip()
    if value == "Yes":
        return 1
    if value == "No":
        return 0
    return cint(default)


def _zg_company_setting(company: str | None, field: str) -> str | None:
    if not company or not frappe.db.exists("DocType", "ZG Company Settings"):
        return None
    return frappe.db.get_value("ZG Company Settings", {"company": company}, field) or None


def _user_company(user: str, profile_warehouse: str | None) -> str | None:
    if profile_warehouse:
        company = frappe.db.get_value("Warehouse", profile_warehouse, "company")
        if company:
            return company
    # The *target* user's own default, then the site-wide one. Deliberately
    # no "first Company on the site" fallback: an unknown company must not
    # silently become some other company's books.
    return (
        frappe.defaults.get_user_default("company", user=user)
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or None
    )


def default_warehouse(company: str | None) -> str | None:
    """Company-level default warehouse: zatgo_core's per-company setting,
    then ERPNext Stock Settings (only if it belongs to that company)."""
    wh = _zg_company_setting(company, "default_warehouse")
    if wh:
        return wh
    wh = frappe.db.get_single_value("Stock Settings", "default_warehouse")
    if wh and (not company or frappe.db.get_value("Warehouse", wh, "company") == company):
        return wh
    return None


def default_cash_account(company: str | None) -> str | None:
    """ERPNext's Mode of Payment "Cash" default account for the company,
    then zatgo_core's ZG Company Settings.default_cash_account."""
    if company:
        account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": CASH_MODE_OF_PAYMENT, "company": company},
            "default_account",
        )
        if account:
            return account
    return _zg_company_setting(company, "default_cash_account")


def resolve(user: str | None = None) -> dict[str, Any]:
    """Effective settings for [user] (default: session user)."""
    uid = user or frappe.session.user
    glob = _global_settings()
    profile = _profile_row(uid)

    company = _user_company(uid, profile.get("warehouse"))
    warehouse = profile.get("warehouse") or default_warehouse(company)
    if warehouse and not company:
        company = frappe.db.get_value("Warehouse", warehouse, "company")

    allow_credit = _override(profile, "allow_credit_sales", glob["allow_credit_sales"])
    payment_type = (profile.get("default_payment_type") or glob["default_payment_type"] or "Cash").strip()
    if payment_type not in PAYMENT_TYPES or (payment_type == "Credit" and not allow_credit):
        payment_type = "Cash"

    return {
        "company": company,
        "warehouse": warehouse,
        "cash_account": profile.get("cash_account") or default_cash_account(company),
        "default_payment_type": payment_type,
        "allow_credit_sales": allow_credit,
        "show_payment_type_on_invoice": _override(
            profile, "show_payment_type_on_invoice", glob["show_payment_type_on_invoice"]
        ),
        "show_warehouse_on_invoice": _override(
            profile, "show_warehouse_on_invoice", glob["show_warehouse_on_invoice"]
        ),
        "allow_warehouse_change": _override(
            profile, "allow_warehouse_change", glob["allow_warehouse_change"]
        ),
        "allow_orders": cint(glob["allow_orders"]),
        "restrict_collections_to_route": _override(
            profile, "restrict_collections_to_route", glob["restrict_collections_to_route"]
        ),
        "max_discount_percent": flt(glob["max_discount_percent"]),
    }


def allowed_warehouse(
    requested: str | None,
    *,
    eff: dict[str, Any] | None = None,
    admin: bool | None = None,
) -> str:
    """The warehouse the caller may act on: their default when none is
    requested; another one only if `allow_warehouse_change` and it belongs
    to the same company (admins: any existing warehouse)."""
    from zatgo_core.services.van_sale_access import is_vansale_admin

    eff = eff if eff is not None else resolve()
    admin = is_vansale_admin() if admin is None else admin
    wh = (requested or "").strip() or eff["warehouse"]
    if not wh:
        frappe.throw(
            "No van warehouse is assigned to your account. Ask an admin to set one "
            "on your VanSale Profile or the company defaults."
        )
    if not frappe.db.exists("Warehouse", wh):
        frappe.throw(f"Warehouse not found: {wh}")
    if wh != eff["warehouse"] and not admin:
        if not eff["allow_warehouse_change"]:
            frappe.throw(
                "Access denied: You can only sell from your assigned warehouse.",
                frappe.PermissionError,
            )
        if eff["company"] and frappe.db.get_value("Warehouse", wh, "company") != eff["company"]:
            frappe.throw("That warehouse belongs to another company.", frappe.PermissionError)
    return wh


def selectable_warehouses() -> list[dict[str, Any]]:
    """Warehouses the caller may pick on the invoice: just their default,
    or every active leaf warehouse of their company when changing is
    allowed."""
    from zatgo_core.services.van_sale_access import is_vansale_admin

    eff = resolve()
    if not (eff["allow_warehouse_change"] or is_vansale_admin()):
        names = [eff["warehouse"]] if eff["warehouse"] else []
    else:
        # Sellable stock only: leaf, enabled, not a Transit warehouse.
        filters: dict[str, Any] = {"is_group": 0, "disabled": 0, "warehouse_type": ["!=", "Transit"]}
        if eff["company"]:
            filters["company"] = eff["company"]
        names = frappe.get_all("Warehouse", filters=filters, pluck="name", order_by="name asc")
    return [
        {"name": n, "is_default": int(n == eff["warehouse"])}
        for n in names
    ]


def resolve_sale(
    *,
    payment_type: str | None,
    warehouse: str | None,
    cash_account: str | None = None,
    user: str | None = None,
) -> dict[str, Any]:
    """Validate and complete the payment type / warehouse / cash account a
    caller asked for against the user's effective settings. Throws on
    anything the settings don't allow — the server is the enforcement point,
    not the app's hidden toggles."""
    from zatgo_core.services.van_sale_access import is_vansale_admin

    eff = resolve(user)
    admin = is_vansale_admin(user)

    # No payment type sent = a caller that predates Cash/Credit (older app
    # builds): keep the old behaviour — no payment type, invoice stays
    # outstanding — rather than silently turning its sales into Cash with an
    # auto Payment Entry. Current app builds always send one explicitly
    # (the settings default when the toggle is hidden).
    ptype = (payment_type or "").strip().title() or None
    if ptype is not None and ptype not in PAYMENT_TYPES:
        frappe.throw(f"Payment type must be Cash or Credit, not {payment_type!r}.")
    if ptype == "Credit" and not eff["allow_credit_sales"] and not admin:
        frappe.throw("Credit sales are not allowed for your account.", frappe.PermissionError)

    wh = allowed_warehouse(warehouse, eff=eff, admin=admin)

    account = None
    if ptype == "Cash":
        company = frappe.db.get_value("Warehouse", wh, "company")
        account = (cash_account or "").strip() if admin and cash_account else None
        account = account or (
            eff["cash_account"] if company == eff["company"] else default_cash_account(company)
        )
        if not account:
            frappe.throw(
                f"No Cash account is set up for {company}: set a default account on "
                "Mode of Payment \"Cash\" for this company, or a Cash Account on the "
                "user's VanSale Profile."
            )

    return {"payment_type": ptype, "warehouse": wh, "cash_account": account}
