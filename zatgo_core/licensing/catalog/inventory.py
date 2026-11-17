"""Inventory: items, warehouses, stock movements, batches, serials, valuation.

Stock Entry is one DocType for several jobs; each feature grants it only for its own `purpose`. The stock
ledger itself (Stock Ledger Entry, Bin, Serial and Batch Bundle, reposting) is never gated (NEVER_GATE)."""

from zatgo_core.licensing.registry import MASTER, SETTINGS, TRANSACTION, Module, dt, feature

MODULE = Module(id="inventory", label="Inventory", category="Business", order=40, icon="stock",
                description="Items, warehouses, stock transfers, adjustments, batches, serials and valuation.")

API = "zatgo_core.api.v1.warehouse."

FEATURES = [
    feature(
        "inventory.items", "Items",
        doctypes=[dt("Item", MASTER), dt("Item Group", MASTER), dt("Brand", MASTER), dt("Item Attribute", MASTER)],
        reports=["Item Variant Details", "Item Where Used"],
        api_prefixes=[API + "items.", API + "item_groups."],
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "inventory.warehouses", "Warehouses",
        doctypes=[dt("Warehouse", MASTER), dt("Warehouse Type", MASTER)],
        pages=["warehouse-capacity-summary"],
        api_prefixes=[API + "warehouses."],
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "inventory.stock_reports", "Stock balance and ledger reports",
        reports=["Stock Ledger", "Stock Balance", "Stock Projected Qty", "Stock Ageing", "Stock Analytics",
                 "Warehouse Wise Stock Balance", "Total Stock Summary", "Item Shortage Report",
                 "Item Balance (Simple)", "Reserved Stock", "Product Bundle Balance"],
        pages=["stock-balance"],
        workspaces=["Stock"],
        api_prefixes=[API + "stock."],
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "inventory.stock_receipt", "Material Receipt",
        doctypes=[dt("Stock Entry", TRANSACTION, purpose="Material Receipt")],
    ),
    feature(
        "inventory.stock_transfer", "Material Transfer",
        doctypes=[dt("Stock Entry", TRANSACTION, purpose="Material Transfer")],
        platforms=["desk", "mobile"],
    ),
    feature(
        "inventory.stock_issue", "Material Issue (damaged / write-off)",
        doctypes=[dt("Stock Entry", TRANSACTION, purpose="Material Issue")],
        platforms=["desk", "mobile"],
    ),
    feature(
        "inventory.reconciliation", "Stock Reconciliation",
        doctypes=[dt("Stock Reconciliation", TRANSACTION)],
    ),
    feature(
        "inventory.batch", "Batch tracking",
        doctypes=[dt("Batch", MASTER)],
        reports=["Batch-Wise Balance History", "Batch Item Expiry Status", "Available Batch Report",
                 "Serial and Batch Summary"],
    ),
    feature(
        "inventory.serial", "Serial number tracking",
        doctypes=[dt("Serial No", MASTER)],
        reports=["Serial No Ledger", "Serial No Status", "Available Serial No", "Serial No and Batch Traceability"],
    ),
    feature(
        "inventory.valuation", "Landed cost and valuation",
        doctypes=[dt("Landed Cost Voucher", TRANSACTION)],
        reports=["Landed Cost Report", "Warehouse wise Item Balance Age and Value",
                 "Stock and Account Value Comparison"],
    ),
    feature(
        "inventory.reorder", "Reorder planning",
        reports=["Itemwise Recommended Reorder Level", "Items To Be Requested"],
    ),
    feature(
        "inventory.pick_pack", "Pick lists and packing slips",
        doctypes=[dt("Pick List", TRANSACTION), dt("Packing Slip", TRANSACTION)],
    ),
    feature(
        "inventory.settings", "Stock settings",
        doctypes=[dt("Stock Settings", SETTINGS), dt("Stock Entry Type", MASTER)],
    ),
]
