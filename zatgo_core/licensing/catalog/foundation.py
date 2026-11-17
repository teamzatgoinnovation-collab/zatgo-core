"""Foundation: what every edition needs to run at all. Part of every edition, never sold separately."""

from zatgo_core.licensing.registry import MASTER, READ_ONLY, SETTINGS, Module, dt, feature

MODULE = Module(
    id="foundation", label="Foundation", category="Foundation", order=0, icon="setting",
    description="Company setup, shared masters (read), users, backups -- included in every edition.",
)

FEATURES = [
    feature(
        "foundation.setup", "Company setup",
        description="Company, currencies, fiscal years, UOMs, price lists, modes of payment, addresses, contacts.",
        doctypes=[
            dt("Company", MASTER), dt("Currency", MASTER), dt("Currency Exchange", MASTER),
            dt("Fiscal Year", MASTER), dt("UOM", MASTER), dt("Price List", MASTER),
            dt("Mode of Payment", MASTER), dt("Terms and Conditions", MASTER), dt("Letter Head", MASTER),
            dt("Address", MASTER), dt("Contact", MASTER), dt("Territory", MASTER), dt("Holiday List", MASTER),
            dt("Branch", MASTER), dt("Department", MASTER), dt("Global Defaults", SETTINGS),
        ],
        workspaces=["Home", "ERPNext Settings"],
        platforms=["desk", "desktop", "mobile"],
        foundation=True,
    ),
    feature(
        "foundation.masters_read", "Shared masters (read)",
        description="Read access to the masters every transaction looks up: customers, suppliers, items, "
        "warehouses, accounts, tax templates. Creating and changing them belongs to the owning module.",
        doctypes=[
            dt(name, READ_ONLY)
            for name in (
                "Customer", "Customer Group", "Supplier", "Supplier Group", "Item", "Item Group", "Item Price",
                "Brand", "Warehouse", "Account", "Cost Center", "Sales Taxes and Charges Template",
                "Purchase Taxes and Charges Template", "Item Tax Template", "Tax Category", "Sales Person",
                "POS Profile", "Payment Terms Template",
            )
        ],
        platforms=["desk", "desktop", "mobile"],
        foundation=True,
    ),
    feature(
        "foundation.users", "Users and roles",
        description="Users, roles, role and module profiles, user permissions, the Role Permission Manager.",
        doctypes=[
            dt("Role Profile", MASTER), dt("Module Profile", MASTER), dt("User Permission", MASTER),
            dt("System Settings", SETTINGS),
        ],
        pages=["permission-manager"],
        workspaces=["Users"],
        source_app="frappe",
        foundation=True,
    ),
    feature(
        "foundation.backup", "Backups",
        description="Download the site's backups. Kept in every edition so data can always leave the site.",
        pages=["backups"],
        source_app="frappe",
        foundation=True,
    ),
]
