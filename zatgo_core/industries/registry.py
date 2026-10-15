"""Industry registry: the one place industries are described.

zatgo_core is CORE (accounting, stock, sales, purchase, ...) plus optional
INDUSTRY modules. Which industries a site exposes is chosen per site in
ZG System Settings -> Industries (stored in that site's database, see
industries/gate.py); this file only says what exists.

Adding an industry = one `Industry(...)` entry below plus, once it has
features, a package under zatgo_core/industries/<key>/ (docs/industries.md).
Industries with `implemented=False` are listed ("coming soon") but cannot be
switched on.
"""

from __future__ import annotations

from dataclasses import dataclass

# Core capabilities an industry can depend on -> a DocType that must exist.
CAPABILITIES = {
    "accounting": "Journal Entry",
    "sales": "Sales Invoice",
    "purchase": "Purchase Invoice",
    "stock": "Stock Entry",
    "item": "Item",
    "customer": "Customer",
    "manufacturing": "Work Order",
}


@dataclass(frozen=True)
class Industry:
    key: str
    label: str
    description: str
    icon: str = "organization"
    # Core capabilities (CAPABILITIES) this industry builds on.
    requires: tuple[str, ...] = ("accounting", "sales", "item")
    # Other industries that must be on before this one.
    requires_industries: tuple[str, ...] = ()
    # Roles created for the industry (granted by the site's admin).
    roles: tuple[str, ...] = ()
    # The industry's own DocTypes: nobody's while it is off.
    doctypes: tuple[str, ...] = ()
    # Whitelisted-method prefixes: 404 while it is off.
    api_prefixes: tuple[str, ...] = ()
    # (label, DocType) shortcuts of its Desk workspace.
    workspace_links: tuple[tuple[str, str], ...] = ()
    features: tuple[str, ...] = ()
    implemented: bool = False

    @property
    def workspace(self) -> str:
        return f"ZatGo {self.label}"


def _stub(key: str, label: str, description: str, icon: str = "organization", **kw) -> Industry:
    return Industry(key=key, label=label, description=description, icon=icon, **kw)


INDUSTRIES: dict[str, Industry] = {
    i.key: i
    for i in (
        Industry(
            key="jewellery",
            label="Jewellery",
            description="Metal, purity, weights, making charge, wastage, hallmark and daily metal rates on Items.",
            icon="gem",
            requires=("accounting", "sales", "purchase", "stock", "item"),
            roles=("ZG Jewellery User", "ZG Jewellery Manager"),
            doctypes=("ZG Metal Rate",),
            api_prefixes=("zatgo_core.api.v1.jewellery.",),
            workspace_links=(("Metal Rate", "ZG Metal Rate"), ("Item", "Item")),
            features=("item_fields", "metal_rates", "price_calculation"),
            implemented=True,
        ),
        Industry(
            key="gym",
            label="Gym",
            description="Members, membership plans, start/end dates, renewals, trainers, attendance and payments.",
            icon="activity",
            requires=("accounting", "sales", "customer"),
            roles=("ZG Gym User", "ZG Gym Manager"),
            doctypes=("ZG Gym Plan", "ZG Gym Membership", "ZG Gym Attendance"),
            api_prefixes=("zatgo_core.api.v1.gym.",),
            workspace_links=(
                ("Membership Plan", "ZG Gym Plan"),
                ("Membership", "ZG Gym Membership"),
                ("Attendance", "ZG Gym Attendance"),
                ("Customer", "Customer"),
            ),
            features=("plans", "memberships", "renewal", "attendance", "billing"),
            implemented=True,
        ),
        Industry(
            key="restaurant",
            label="Restaurant",
            description="Floor tables, orders, kitchen tickets (KDS), dine-in / takeaway and billing (Resto POS).",
            icon="utensils",
            requires=("accounting", "sales", "item", "stock"),
            roles=(),
            doctypes=("ZG Table", "ZG Order", "ZG Order Item", "ZG KDS Ticket"),
            api_prefixes=("zatgo_core.api.v1.resto_pos.",),
            workspace_links=(
                ("Tables", "ZG Table"),
                ("Orders", "ZG Order"),
                ("Kitchen Tickets", "ZG KDS Ticket"),
            ),
            features=("tables", "orders", "kds", "billing"),
            implemented=True,
        ),
        _stub("textile", "Textile", "Fabric, brand, colour, size, pattern, design, roll length/width, variants.", "layers"),
        _stub("supermarket", "Supermarket", "Barcode-heavy fast POS, multiple units, batch/expiry, offers.", "shopping-cart"),
        _stub("salon", "Salon", "Services, staff, duration, appointments, packages and memberships.", "scissors"),
        _stub("electrical", "Electrical Shop", "Brands, specifications, warranty and serial numbers.", "zap"),
        _stub("retail", "General Retail", "General retail trade.", "shopping-bag"),
        _stub("wholesale", "Wholesale", "Bulk trade and price lists.", "package"),
        _stub("distribution", "Distribution", "Distribution and routes.", "truck"),
        _stub("pharmacy", "Pharmacy", "Medicines with batch and expiry.", "pill", requires=("accounting", "sales", "item", "stock")),
        _stub("electronics", "Electronics", "Electronics with warranty and serial numbers.", "cpu"),
        _stub("hardware", "Hardware", "Hardware store.", "tool"),
        _stub("mobile", "Mobile & Accessories", "Mobile phones and accessories (IMEI).", "smartphone"),
        _stub("automobile", "Automobile & Spare Parts", "Spare parts with vehicle compatibility.", "car"),
        _stub("service", "Service Business", "Service jobs and billing.", "briefcase"),
        _stub(
            "manufacturing",
            "Manufacturing",
            "Production on top of ERPNext Manufacturing.",
            "settings",
            requires=("accounting", "sales", "item", "stock", "manufacturing"),
        ),
    )
}


def get(key: str) -> Industry | None:
    return INDUSTRIES.get(key)


def validate_registry() -> list[str]:
    """Problems with the registry itself (empty = consistent)."""
    problems: list[str] = []
    for key, ind in INDUSTRIES.items():
        if ind.key != key:
            problems.append(f"{key}: key mismatch")
        for cap in ind.requires:
            if cap not in CAPABILITIES:
                problems.append(f"{key}: unknown capability {cap}")
        for dep in ind.requires_industries:
            if dep not in INDUSTRIES:
                problems.append(f"{key}: unknown industry dependency {dep}")
    # cycles among industries
    for key in INDUSTRIES:
        seen: set[str] = set()
        stack = list(INDUSTRIES[key].requires_industries)
        while stack:
            cur = stack.pop()
            if cur == key:
                problems.append(f"{key}: dependency cycle")
                break
            if cur in seen or cur not in INDUSTRIES:
                continue
            seen.add(cur)
            stack.extend(INDUSTRIES[cur].requires_industries)
    owner: dict[str, str] = {}
    for key, ind in INDUSTRIES.items():
        for dt in ind.doctypes:
            if dt in owner:
                problems.append(f"{dt}: owned by {owner[dt]} and {key}")
            owner[dt] = key
    return problems


def doctype_owner() -> dict[str, str]:
    """DocType name -> industry key (static; no DB, no disk scan)."""
    return {dt: key for key, ind in INDUSTRIES.items() for dt in ind.doctypes}
