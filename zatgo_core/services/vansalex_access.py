"""VanSaleX modules & features — what this client (site) and user may use.

One VanSaleX app build serves every client; each client is its own ERPNext
site. What a site's drivers get is configured here, server-side, and the app
only renders it (`vansalex.me.context` → `access`):

- `CATALOG` defines every key (stable machine identifiers — never page
  titles). Adding a key: add it here, mirror it in the app's
  `lib/core/access/feature_registry.dart`, and gate the endpoint/UI.
- `VanSaleX Settings.access` (child table `VanSaleX Access`) holds the
  client's on/off per key; `ensure_vansalex_access` adds missing rows on
  migrate without touching existing ones. A key with no row uses its
  catalog `default` (on for what VanSaleX already did before this existed,
  off for anything new — fail-closed).
- `ZG Van Sale Profile.access_overrides` can switch a row key OFF for one
  driver, never on beyond the client. Derived keys keep their existing
  per-driver controls (e.g. the profile's Allow Credit Sales override).
- A few keys mirror an existing setting rather than a row (`derived`), so
  there is still one place to change them: e.g. `sales_order` is
  `VanSaleX Settings.allow_orders`.
- A feature is only on while its parent module is.

Effective rule per key: client on AND not disabled on the profile AND parent
module on. It binds every VanSaleX API caller (admins too — it's the
client's licence); the DocType backstop (`check_doc_access`) applies it to
field users on any entry point (shared REST endpoints, Desk).

Hiding something in the app is not the control — `require_*` here is.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt

SETTINGS_DOCTYPE = "VanSaleX Settings"
PROFILE_DOCTYPE = "ZG Van Sale Profile"

MODULE = "Module"
FEATURE = "Feature"

# key: (kind, label, parent module, default when the client has no row,
#       derived-from setting or None)
CATALOG: dict[str, tuple[str, str, str | None, int, str | None]] = {
    # -- modules (in the order the app shows them; More-tab entries in its order)
    "dashboard": (MODULE, "Dashboard", None, 1, None),
    "sales_invoice": (MODULE, "Sales Invoice", None, 1, None),
    "sales_order": (MODULE, "Sales Orders (invoice later)", None, 1, "allow_orders"),
    "route_plan": (MODULE, "Plan & Route", None, 1, None),
    "customers": (MODULE, "Customers", None, 1, None),
    "sales_return": (MODULE, "Sales Returns", None, 1, None),
    "collections": (MODULE, "Collections", None, 1, None),
    "products": (MODULE, "Products", None, 1, None),
    "reports": (MODULE, "Reports", None, 1, None),
    "activities": (MODULE, "Activities", None, 1, None),
    "documents": (MODULE, "Documents", None, 1, None),
    "my_performance": (MODULE, "My Performance", None, 1, None),
    "inventory": (MODULE, "Van Stock", None, 1, None),
    # -- features ----------------------------------------------------------------
    # Printing covers invoices and credit notes alike, so no parent module.
    "sales_invoice.print_a4": (FEATURE, "Print A4 (invoices & credit notes)", None, 1, None),
    "sales_invoice.print_80mm": (FEATURE, "Print 80mm thermal (invoices & credit notes)", None, 1, None),
    "sales_invoice.multiple_payment_modes": (
        FEATURE, "Split payment across methods", "sales_invoice", 1, None,
    ),
    "sales_invoice.multiple_payment_accounts": (
        FEATURE, "Choose payment account", "sales_invoice", 1, None,
    ),
    "sales_invoice.credit_sale": (FEATURE, "Credit sales", "sales_invoice", 1, "allow_credit_sales"),
    # Both discounts are also capped by VanSaleX Settings → Max Discount %
    # (and off while it is 0) — see REQUIRES_SETTING.
    "sales_invoice.discount": (FEATURE, "Total discount", "sales_invoice", 1, None),
    "sales_invoice.line_discount": (FEATURE, "Discount per item line", "sales_invoice", 0, None),
    "sales_invoice.change_warehouse": (
        FEATURE, "Change warehouse", "sales_invoice", 0, "allow_warehouse_change",
    ),
    # New functionality: off until an admin turns it on.
    "sales_invoice.edit_rate": (FEATURE, "Edit item rate", "sales_invoice", 0, None),
    "collections.card": (FEATURE, "Card / non-cash collection", "collections", 1, None),
    "collections.multiple_payment_modes": (
        FEATURE, "Split collection across methods", "collections", 1, None,
    ),
}

# Where each key shows in the app — shown beside the switch in VanSaleX
# Settings so an admin can match a row to the screen. "More → X" rows are
# the app's More tab, in its order; Settings (with Logout) is always there.
APP_LOCATION: dict[str, str] = {
    "dashboard": "Home tab",
    "sales_invoice": "Orders tab, More → Sales Orders, New Invoice",
    "sales_order": "New Order, Convert to Invoice",
    "route_plan": "More → Plan & Route",
    "customers": "More → Customers, Customers quick action",
    "sales_return": "More → Sales Returns, Sales Return quick action",
    "collections": "Collection tab, More → Collections, New Collection",
    "products": "More → Products, Products quick action",
    "reports": "More → Reports (incl. aging report)",
    "activities": "More → Activities",
    "documents": "More → Documents",
    "my_performance": "More → My Performance",
    "inventory": "Home → Van Stock card and summary",
    "sales_invoice.print_a4": "Print sheet → A4",
    "sales_invoice.print_80mm": "Print sheet → 80mm thermal",
    "sales_invoice.multiple_payment_modes": "New Invoice → Split payment (several methods)",
    "sales_invoice.multiple_payment_accounts": "New Invoice → Split payment → Account",
    "sales_invoice.credit_sale": "New Invoice → Cash / Credit",
    "sales_invoice.discount": "New Invoice / New Order → Discount % (whole invoice)",
    "sales_invoice.line_discount": "New Invoice / New Order → Disc % on each line",
    "sales_invoice.change_warehouse": "New Invoice → Warehouse",
    "sales_invoice.edit_rate": "New Invoice / New Order → Rate on each line",
    "collections.card": "New Collection → Card",
    "collections.multiple_payment_modes": "New Collection → Split payment",
}

# Keys that also need a VanSaleX Settings value: on only while it is set
# (Max Discount % above 0 for the discounts).
REQUIRES_SETTING: dict[str, str] = {
    "sales_invoice.discount": "max_discount_percent",
    "sales_invoice.line_discount": "max_discount_percent",
}

# A key that used to be derived from a setting starts, as a row, from that
# setting — so turning it into a switch changes nothing on upgrade.
SEED_FROM_SETTING: dict[str, str] = {
    "sales_invoice.discount": "max_discount_percent",
}

# Keys split out of an existing one: a site getting them starts from that
# key's current switch, so nothing appears or disappears by upgrading.
SPLIT_FROM: dict[str, str] = {
    "activities": "route_plan",
    "documents": "sales_invoice",
    "my_performance": "reports",
}

MODULE_KEYS = tuple(k for k, v in CATALOG.items() if v[0] == MODULE)
FEATURE_KEYS = tuple(k for k, v in CATALOG.items() if v[0] == FEATURE)
# Keys with a row in VanSaleX Settings.access (derived keys have none).
ROW_KEYS = tuple(k for k, v in CATALOG.items() if not v[4])


def _client_rows() -> dict[str, int]:
    if not frappe.db.exists("DocType", "VanSaleX Access"):
        return {}
    rows = frappe.get_all(
        "VanSaleX Access",
        filters={"parenttype": SETTINGS_DOCTYPE, "parentfield": "access"},
        fields=["access_key", "enabled"],
    )
    return {r.access_key: cint(r.enabled) for r in rows}


def _profile_disabled(user: str) -> set[str]:
    if not frappe.db.exists("DocType", "ZG Van Sale Profile Access"):
        return set()
    profile = frappe.db.get_value(PROFILE_DOCTYPE, {"user": user, "enabled": 1}, "name")
    if not profile:
        return set()
    rows = frappe.get_all(
        "ZG Van Sale Profile Access",
        filters={"parenttype": PROFILE_DOCTYPE, "parent": profile, "disabled": 1},
        pluck="access_key",
    )
    return set(rows)


def _derived(setting: str, settings: dict[str, Any]) -> int:
    value = settings.get(setting)
    if setting == "max_discount_percent":
        return 1 if flt(value) > 0 else 0
    return 1 if cint(value) else 0


def config_version() -> int:
    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        return 0
    return cint(frappe.db.get_single_value(SETTINGS_DOCTYPE, "config_version"))


def effective(user: str | None = None) -> dict[str, Any]:
    """Effective modules/features for [user] (default: session user)."""
    from zatgo_core.services.vansalex_settings import resolve

    uid = user or frappe.session.user
    client = _client_rows()
    disabled = _profile_disabled(uid)
    settings = resolve(uid)

    base: dict[str, int] = {}
    for key, (_kind, _label, _parent, default, derived) in CATALOG.items():
        on = _derived(derived, settings) if derived else client.get(key, default)
        if on and key in REQUIRES_SETTING:
            on = _derived(REQUIRES_SETTING[key], settings)
        base[key] = 1 if on and (derived or key not in disabled) else 0

    def _on(key: str) -> bool:
        parent = CATALOG[key][2]
        return bool(base[key]) and (parent is None or bool(base[parent]))

    return {
        "modules": {k: _on(k) for k in MODULE_KEYS},
        "features": {k: _on(k) for k in FEATURE_KEYS},
        "config_version": config_version(),
    }


def is_enabled(key: str, user: str | None = None, eff: dict[str, Any] | None = None) -> bool:
    if key not in CATALOG:
        return False
    eff = eff or effective(user)
    group = "modules" if CATALOG[key][0] == MODULE else "features"
    return bool(eff[group].get(key))


def _label(key: str) -> str:
    return CATALOG[key][1] if key in CATALOG else key


def require(*keys: str) -> None:
    """Pass if ANY of [keys] is enabled for the session user."""
    eff = effective()
    if any(is_enabled(k, eff=eff) for k in keys):
        return
    names = " / ".join(_label(k) for k in keys)
    frappe.throw(
        f"{names} is not enabled for your account. Ask your admin to turn it on "
        "in ERPNext → VanSaleX Settings → Modules & Features.",
        frappe.PermissionError,
    )


# -- payment rows (split payment / account choice) -------------------------------


def check_payment_rows(rows: list[dict[str, Any]], company: str, scope: str) -> None:
    """[scope] is "sales_invoice" or "collections". More than one payment
    method needs `<scope>.multiple_payment_modes`; on an invoice, an account
    other than the method's default needs `.multiple_payment_accounts`."""
    from zatgo_core.services.payment_allocation import default_account

    if not rows:
        return
    if len({r["mode_of_payment"] for r in rows}) > 1 or len(rows) > 1:
        require(f"{scope}.multiple_payment_modes")
    if scope == "sales_invoice":
        for r in rows:
            if r.get("account") and r["account"] != default_account(r["mode_of_payment"], company):
                require("sales_invoice.multiple_payment_accounts")
                break
    if scope == "collections":
        for r in rows:
            check_collection_method(r["mode_of_payment"])


def check_item_rates(rows: list[dict[str, Any]], price_list: str | None = None) -> None:
    """Without `sales_invoice.edit_rate`, a line's rate must be the item's
    price — its standard selling rate (what the app shows), else its rate on
    [price_list] (the customer's). 0 / blank lets ERPNext fill the price in.
    An item with no price anywhere has nothing to compare against and is
    left to the caller. With the feature, any positive rate is accepted."""
    if is_enabled("sales_invoice.edit_rate"):
        return
    for row in rows:
        rate = flt(row.get("rate"))
        if rate <= 0:
            continue
        code = row.get("item_code")
        price = flt(frappe.db.get_value("Item", code, "standard_rate"))
        if price <= 0 and price_list:
            price = flt(
                frappe.db.get_value("Item Price", {"item_code": code, "price_list": price_list}, "price_list_rate")
            )
        if price > 0 and abs(rate - price) > 0.005:
            frappe.throw(
                f"Changing the rate isn't enabled for your account ({code}: "
                f"{price:.2f}, not {rate:.2f}). Ask your admin to turn on 'Edit item rate' "
                "in ERPNext → VanSaleX Settings → Modules & Features.",
                frappe.PermissionError,
            )


def check_collection_method(mode_of_payment: str | None) -> None:
    """A non-cash Mode of Payment (type other than Cash) needs collections.card."""
    mop = (mode_of_payment or "").strip()
    if not mop:
        return
    mop_type = frappe.db.get_value("Mode of Payment", mop, "type")
    if mop_type and mop_type != "Cash":
        require("collections.card")


# -- DocType backstop (field users, any entry point) ------------------------------


def _is_field_user(user: str) -> bool:
    profile = frappe.db.get_value(
        PROFILE_DOCTYPE, {"user": user, "enabled": 1}, "user_type"
    )
    return bool(profile) and profile != "Admin"


def check_doc_access(doc, method=None) -> None:
    """before_insert on Sales Invoice / Sales Order / Payment Entry, before_save
    (create and edit) on Customer / Item. Only for field users (enabled ZG Van Sale Profile, not Admin):
    covers the shared accounting/warehouse endpoints, /api/resource and Desk,
    which the vansalex endpoint checks don't."""
    user = frappe.session.user
    if user in ("Administrator", "Guest") or not _is_field_user(user):
        return
    dt = doc.doctype
    if dt == "Sales Invoice":
        require("sales_return" if cint(doc.get("is_return")) else "sales_invoice")
    elif dt == "Sales Order":
        require("sales_order")
    elif dt == "Payment Entry":
        # The Cash invoice's own Payment Entry is part of the sale, not a
        # collection (invoice_cash_payment_service sets this flag).
        if doc.payment_type == "Receive" and not doc.flags.get("zatgo_auto_cash_payment"):
            require("collections")
    elif dt == "Customer":
        require("customers")
    elif dt == "Item":
        require("products")
