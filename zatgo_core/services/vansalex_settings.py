"""Effective VanSaleX settings for a user.

Company-wide defaults live in the `VanSaleX Settings` single; a user's
`ZG Van Sale Profile` may override them (blank / "Inherit" = use the
default). Account and warehouse defaults come from ERPNext's own records
first and zatgo_core's second:

- warehouse:    Profile.warehouse → ZG Company Settings.default_warehouse
                → ERPNext Stock Settings.default_warehouse
- cash account: Profile.cash_account → VanSaleX Settings
                .default_cash_account (if it is the company's) → ERPNext
                Mode of Payment "Cash" default account for the company →
                ZG Company Settings.default_cash_account
- bank account: Profile.bank_account → VanSaleX Settings
                .default_bank_account (if it is the company's) → the
                company's default account on a Bank-type Mode of Payment
                ("Bank" first, as the Sales Invoice form pre-fills it) →
                ERPNext Company.default_bank_account
  A driver may sell into another Cash / Bank account of the company only
  with the "Choose payment account" feature (vansalex_access).
- sales taxes:  ZG Company Settings.default_tax_template → the company's
                default ERPNext Sales Taxes and Charges Template
                (is_default) → its first enabled one
- print format: ERPNext's default print format for Sales Invoice (the
                site's Customize Form setting) → "VanSale Tax Invoice"

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
PAYMENT_TYPES = ("Cash", "Bank", "Credit")
# Payment type -> the Sales Invoice field its account goes in, and the
# Account Type that account must have (see invoice_cash_payment_service).
ACCOUNT_PAYMENT_TYPES = {"Cash": "cash_account", "Bank": "bank_account"}

_DEFAULTS: dict[str, Any] = {
    "default_payment_type": "Cash",
    "allow_credit_sales": 1,
    # New: off until an admin turns it on.
    "allow_bank_payment": 0,
    "default_cash_account": "",
    "default_bank_account": "",
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


def check_account(
    account: str | None, account_type: str, label: str, company: str | None = None
) -> None:
    """[account] must be an enabled ledger (not group) account of
    [account_type] -- and of [company], when given. Blank passes."""
    if not account:
        return
    row = frappe.db.get_value(
        "Account", account, ["company", "account_type", "is_group", "disabled"], as_dict=True
    )
    if not row:
        frappe.throw(f"{label}: account {account} does not exist.")
    if row.is_group or cint(row.disabled) or row.account_type != account_type:
        frappe.throw(
            f"{label}: {account} is not an enabled {account_type}-type ledger account "
            f"(Account Type = {account_type}, not a group)."
        )
    if company and row.company != company:
        frappe.throw(f"{label}: {account} belongs to {row.company}, not {company}.")


def _usable_account(account: str | None, company: str | None, account_type: str) -> str | None:
    """[account] if it can take [account_type] payments for [company]."""
    if not account or not company:
        return None
    row = frappe.db.get_value(
        "Account", account, ["company", "account_type", "is_group", "disabled"], as_dict=True
    )
    if not row or row.company != company or row.account_type != account_type:
        return None
    return None if row.is_group or cint(row.disabled) else account


def default_cash_account(company: str | None) -> str | None:
    """VanSaleX Settings' Default Cash Account (when it is this company's),
    ERPNext's Mode of Payment "Cash" default account for the company, then
    zatgo_core's ZG Company Settings.default_cash_account."""
    account = _usable_account(_global_settings()["default_cash_account"], company, "Cash")
    if account:
        return account
    if company:
        account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": CASH_MODE_OF_PAYMENT, "company": company},
            "default_account",
        )
        if account:
            return account
    return _zg_company_setting(company, "default_cash_account")


def default_bank_account(company: str | None) -> str | None:
    """VanSaleX Settings' Default Bank Account (when it is this company's),
    then the company's default account on an enabled Bank-type Mode of
    Payment -- "Bank" first, then by name, as the Sales Invoice form
    pre-fills it -- then ERPNext's Company.default_bank_account."""
    account = _usable_account(_global_settings()["default_bank_account"], company, "Bank")
    if account or not company:
        return account
    modes = frappe.get_all(
        "Mode of Payment", filters={"type": "Bank", "enabled": 1}, pluck="name", order_by="name asc"
    )
    modes.sort(key=lambda m: m.lower() != "bank")
    for mode in modes:
        account = _usable_account(
            frappe.db.get_value(
                "Mode of Payment Account", {"parent": mode, "company": company}, "default_account"
            ),
            company,
            "Bank",
        )
        if account:
            return account
    return _usable_account(
        frappe.db.get_value("Company", company, "default_bank_account"), company, "Bank"
    )


def sales_tax_template(company: str | None) -> tuple[str | None, bool]:
    """(Sales Taxes and Charges Template, prices-are-tax-inclusive) for
    [company]: zatgo_core's per-company choice first, then ERPNext's own
    default template for the company."""
    template = _zg_company_setting(company, "default_tax_template")
    inclusive = bool(cint(_zg_company_setting(company, "enable_tax_inclusive") or 0))
    if not company or not frappe.db.exists("DocType", "Sales Taxes and Charges Template"):
        return template, inclusive
    if not template:
        filters = {"company": company, "disabled": 0}
        template = frappe.db.get_value(
            "Sales Taxes and Charges Template", {**filters, "is_default": 1}, "name"
        ) or frappe.db.get_value("Sales Taxes and Charges Template", filters, "name")
    if template and not frappe.db.exists("Sales Taxes and Charges Template", template):
        template = None
    return template, inclusive


def tax_summary(company: str | None) -> dict[str, Any]:
    """What the app needs to show VAT before the invoice exists: the
    template name and its combined percentage on net total. The server
    still computes the real figures through ERPNext on submit."""
    template, inclusive = sales_tax_template(company)
    rate = 0.0
    if template:
        rows = frappe.get_all(
            "Sales Taxes and Charges",
            filters={"parent": template, "parenttype": "Sales Taxes and Charges Template"},
            fields=["charge_type", "rate", "included_in_print_rate"],
        )
        on_net = [r for r in rows if r.charge_type == "On Net Total"]
        rate = sum(flt(r.rate) for r in on_net)
        inclusive = inclusive or (bool(on_net) and all(cint(r.included_in_print_rate) for r in on_net))
    return {"tax_template": template, "tax_rate": rate, "tax_inclusive": int(inclusive)}


def default_print_format() -> str:
    """The site's default Sales Invoice print format, as set in ERPNext
    (Customize Form → Default Print Format)."""
    from zatgo_core.setup.ensure_print_formats import PRINT_FORMAT_NAME

    fmt = frappe.get_meta("Sales Invoice").default_print_format
    if fmt and frappe.db.get_value("Print Format", fmt, "disabled") == 0:
        return fmt
    return PRINT_FORMAT_NAME


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
    allow_bank = _override(profile, "allow_bank_payment", glob["allow_bank_payment"])
    payment_type = (profile.get("default_payment_type") or glob["default_payment_type"] or "Cash").strip()
    if (
        payment_type not in PAYMENT_TYPES
        or (payment_type == "Credit" and not allow_credit)
        or (payment_type == "Bank" and not allow_bank)
    ):
        payment_type = "Cash"

    return {
        "company": company,
        "warehouse": warehouse,
        "cash_account": profile.get("cash_account") or default_cash_account(company),
        "bank_account": profile.get("bank_account") or default_bank_account(company),
        "default_payment_type": payment_type,
        "allow_credit_sales": allow_credit,
        "allow_bank_payment": allow_bank,
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
        **tax_summary(company),
        "print_format": default_print_format(),
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


def _account_choices(company: str | None, account_type: str, default: str | None, choose: bool) -> list[str]:
    names = [default] if default else []
    if choose and company:
        for name in frappe.get_all(
            "Account",
            filters={"company": company, "account_type": account_type, "is_group": 0, "disabled": 0},
            pluck="name",
            order_by="name asc",
        ):
            if name not in names:
                names.append(name)
    return names


def selectable_payment_accounts() -> dict[str, list[dict[str, Any]]]:
    """Cash and Bank accounts the caller may sell into, default first: every
    enabled Cash- / Bank-type ledger account of their company with the
    "Choose payment account" feature, otherwise just the default."""
    from zatgo_core.services.vansalex_access import is_enabled

    eff = resolve()
    choose = is_enabled("sales_invoice.multiple_payment_accounts")
    out: dict[str, list[dict[str, Any]]] = {}
    for ptype, key in ACCOUNT_PAYMENT_TYPES.items():
        default = eff[key]
        out[key] = [
            {"name": n, "is_default": int(n == default)}
            for n in _account_choices(eff["company"], ptype, default, choose)
        ]
    return out


def _sale_account(ptype: str, *, requested: str | None, default: str | None, company: str | None) -> str:
    """The Cash / Bank account a sale goes into: the one asked for -- which,
    unless it is the default, needs "Choose payment account" -- else the
    default. Checked here so a wrong one fails before anything is saved."""
    from zatgo_core.services.vansalex_access import require

    requested = (requested or "").strip()
    if requested and requested != default:
        require("sales_invoice.multiple_payment_accounts")
    account = requested or default
    if not account:
        where = (
            'a default account on Mode of Payment "Cash" for this company, a Default '
            "Cash Account in VanSaleX Settings, or a Cash Account on the user's VanSale Profile"
            if ptype == "Cash"
            else "a Default Bank Account in VanSaleX Settings, or a Bank Account on the "
            "user's VanSale Profile"
        )
        frappe.throw(f"No {ptype} account is set up for {company}: set {where}.")
    check_account(account, ptype, f"{ptype} Account", company)
    return account


def resolve_sale(
    *,
    payment_type: str | None,
    warehouse: str | None,
    cash_account: str | None = None,
    bank_account: str | None = None,
    bank_reference_no: str | None = None,
    user: str | None = None,
) -> dict[str, Any]:
    """Validate and complete the payment type / warehouse / Cash or Bank
    account a caller asked for against the user's effective settings.
    Throws on anything the settings don't allow — the server is the
    enforcement point, not the app's hidden toggles."""
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
        frappe.throw(f"Payment type must be Cash, Bank or Credit, not {payment_type!r}.")
    if ptype == "Credit" and not eff["allow_credit_sales"] and not admin:
        frappe.throw("Credit sales are not allowed for your account.", frappe.PermissionError)
    if ptype == "Bank" and not eff["allow_bank_payment"] and not admin:
        frappe.throw("Bank payments are not allowed for your account.", frappe.PermissionError)
    if ptype == "Bank" and not frappe.get_meta("Sales Invoice").has_field("custom_bank_account"):
        frappe.throw("Bank payments need zatgo_core's Bank Account field on Sales Invoice: run bench migrate.")

    wh = allowed_warehouse(warehouse, eff=eff, admin=admin)

    sale: dict[str, Any] = {
        "payment_type": ptype,
        "warehouse": wh,
        "cash_account": None,
        "bank_account": None,
        "bank_reference_no": None,
    }
    if ptype in ACCOUNT_PAYMENT_TYPES:
        company = frappe.db.get_value("Warehouse", wh, "company")
        key = ACCOUNT_PAYMENT_TYPES[ptype]
        if company == eff["company"]:
            default = eff[key]
        else:
            default = default_cash_account(company) if ptype == "Cash" else default_bank_account(company)
        sale[key] = _sale_account(
            ptype,
            requested=cash_account if ptype == "Cash" else bank_account,
            default=default,
            company=company,
        )
    if ptype == "Bank":
        # Transfer / cheque no. for the Payment Entry; blank = the invoice no.
        sale["bank_reference_no"] = (bank_reference_no or "").strip()[:140] or None
    return sale
