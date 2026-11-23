"""ZatGo's own apps, VanSaleX and industries -- bridges to the registries that already exist.

These features do not repeat what those registries say: `app_key` points at services/app_catalog.py (switch,
API prefixes, workspaces), `industry` at industries/registry.py, `vansalex_keys` at services/vansalex_access.py.
A licence that includes a feature *allows* the app; the site's switch still decides whether it is on."""

from zatgo_core.licensing.registry import Module, feature

MODULES = [
    Module(id="zatgo_apps", label="ZatGo Apps", category="ZatGo", order=100, icon="apps", source_app="zatgo_core",
           description="ZatGo AI, Tracker, Space, MyBis, Duplicate Prevention and the Desk add-ons."),
    Module(id="vansalex", label="ZatGo VanSaleX", category="ZatGo", order=105, icon="van", source_app="zatgo_core",
           description="The van-sales mobile / web app and its modules."),
    Module(id="industries", label="Industries", category="ZatGo", order=110, icon="organization",
           source_app="zatgo_core", description="Industry add-ons (jewellery, gym, restaurant, textile, supermarket)."),
]
MODULE = MODULES[0]


def _app(fid: str, label: str, app_key: str, workspaces=(), platforms=("desk",), **kw):
    return feature(fid, label, app_key=app_key, workspaces=list(workspaces), platforms=list(platforms),
                   source_app="zatgo_core", **kw)


def _vx(key: str, label: str, requires: dict | None = None, extra_keys=()):
    """One VanSaleX module key (plus its sub-feature keys) as a feature; always needs the app itself."""
    return feature(f"vansalex.{key}", label, vansalex_keys=[key, *extra_keys], platforms=["mobile"],
                   source_app="zatgo_core", requires={"vansalex.app": [], **(requires or {})})


FEATURES = [
    # -- ZatGo apps
    _app("zatgo_apps.chat_ai", "ZatGo AI", "chat_ai", ["ZatGo AI"]),
    _app("zatgo_apps.tracker", "ZatGo Tracker", "tracker", ["ZatGo Tracker"],
         pages=["tracker-hours", "tracker-org", "tracker-workbench"]),
    _app("zatgo_apps.zatgo_space", "ZatGo Space", "zatgo_space", ["ZatGo Space"]),
    _app("zatgo_apps.mybis", "ZatGo MyBis", "mybis", ["ZatGo MyBis"], platforms=("desk", "mobile")),
    _app("zatgo_apps.duplicate_prevention", "Duplicate Prevention", "duplicate_prevention"),
    _app("zatgo_apps.desk_theme", "ZatGo Desk Theme", "saas_theme", ["ZatGo Desk Theme"]),
    _app("zatgo_apps.language_switcher", "ZatGo Language Switcher", "language_switcher",
         ["ZatGo Language Switcher"]),
    # -- VanSaleX
    _app("vansalex.app", "ZatGo VanSaleX app", "vansalex", ["ZatGo VanSaleX"], platforms=("desk", "mobile")),
    _app("vansalex.web", "ZatGo VanSaleX in the browser", "vansalex_web", ["ZatGo VanSaleX Web"],
         platforms=("mobile",), requires={"vansalex.app": []}),
    _vx("dashboard", "VanSaleX dashboard"),
    # A cash invoice from the app also books its Payment Entry (services/invoice_cash_payment_service.py).
    _vx("sales_invoice", "VanSaleX sales invoices",
        {"sales.invoice": ["create", "submit"], "accounting.payment_entry": ["create", "submit"]},
        extra_keys=("sales_invoice.print_a4", "sales_invoice.print_80mm", "sales_invoice.multiple_payment_modes",
                    "sales_invoice.multiple_payment_accounts", "sales_invoice.credit_sale",
                    "sales_invoice.bank_payment", "sales_invoice.discount", "sales_invoice.line_discount",
                    "sales_invoice.change_warehouse", "sales_invoice.edit_rate")),
    _vx("sales_order", "VanSaleX sales orders", {"sales.order": ["create", "submit"]}),
    _vx("sales_return", "VanSaleX sales returns", {"sales.return": ["create", "submit"]}),
    _vx("purchase_invoice", "VanSaleX purchase invoices", {"procurement.purchase_invoice": ["create", "submit"]}),
    _vx("purchase_order", "VanSaleX purchase orders", {"procurement.purchase_order": ["create", "submit"]}),
    _vx("purchase_return", "VanSaleX purchase returns", {"procurement.purchase_return": ["create", "submit"]}),
    _vx("customers", "VanSaleX customers", {"sales.customers": ["create", "write"]}),
    _vx("collections", "VanSaleX collections", {"accounting.payment_entry": ["create", "submit"]},
        extra_keys=("collections.card", "collections.multiple_payment_modes")),
    _vx("route_plan", "VanSaleX plan and route"),
    _vx("products", "VanSaleX products"),
    _vx("reports", "VanSaleX reports"),
    _vx("activities", "VanSaleX activities"),
    _vx("documents", "VanSaleX documents"),
    _vx("my_performance", "VanSaleX my performance"),
    _vx("inventory", "VanSaleX van stock", {"inventory.stock_reports": ["read"]}),
    # A field user's stock transfers / write-offs are their own VanSaleX keys and touch the stock ledger.
    feature(
        "vansalex.stock_transfer", "VanSaleX stock transfers", vansalex_keys=["inventory.transfer"],
        platforms=["mobile"], source_app="zatgo_core",
        requires={"vansalex.inventory": [], "inventory.stock_transfer": ["create", "submit"]},
    ),
    feature(
        "vansalex.stock_write_off", "VanSaleX stock write-off", vansalex_keys=["inventory.adjust"],
        platforms=["mobile"], source_app="zatgo_core",
        requires={"vansalex.inventory": [], "inventory.stock_issue": ["create", "submit"]},
    ),
    # -- Industries
    feature("industries.jewellery", "Jewellery", industry="jewellery", source_app="zatgo_core",
            requires={"inventory.items": ["create", "write"]}),
    feature("industries.gym", "Gym", industry="gym", source_app="zatgo_core",
            requires={"sales.customers": ["create", "write"]}),
    feature("industries.restaurant", "Restaurant", industry="restaurant", source_app="zatgo_core",
            platforms=["desk", "desktop"], requires={"pos.zatgo_pos": []}),
    feature("industries.textile", "Textile", industry="textile", source_app="zatgo_core",
            requires={"inventory.items": ["create", "write"]}),
    feature("industries.supermarket", "Supermarket", industry="supermarket", source_app="zatgo_core",
            platforms=["desk", "desktop"], requires={"pos.zatgo_pos": []}),
]
