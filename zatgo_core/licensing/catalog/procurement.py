"""Procurement: suppliers, requests, RFQs, purchase orders, receipts, invoices, returns."""

from zatgo_core.licensing.registry import MASTER, SETTINGS, TRANSACTION, Module, dt, feature

MODULE = Module(id="procurement", label="Procurement", category="Business", order=30, icon="buying",
                description="Suppliers, material requests, RFQs, purchase orders, receipts and invoices.")

API = "zatgo_core.api.v1.accounting."

FEATURES = [
    feature(
        "procurement.suppliers", "Suppliers",
        doctypes=[dt("Supplier", MASTER), dt("Supplier Group", MASTER)],
        reports=["Procurement Tracker"],
        api_prefixes=[API + "suppliers."],
        platforms=["desk", "desktop"],
    ),
    feature(
        "procurement.material_request", "Material Requests",
        doctypes=[dt("Material Request", TRANSACTION)],
        reports=["Requested Items to Order and Receive", "Requested Items To Be Transferred",
                 "Pending SO Items For Purchase Request"],
    ),
    feature(
        "procurement.rfq", "Requests for Quotation and Supplier Quotations",
        doctypes=[dt("Request for Quotation", TRANSACTION), dt("Supplier Quotation", TRANSACTION)],
        reports=["Supplier Quotation Comparison",
                 "Material Requests for which Supplier Quotations are not created"],
    ),
    feature(
        "procurement.purchase_order", "Purchase Orders",
        doctypes=[dt("Purchase Order", TRANSACTION)],
        reports=["Purchase Order Analysis", "Purchase Order Trends"],
        workspaces=["Buying"],
    ),
    feature(
        "procurement.purchase_receipt", "Purchase Receipts",
        doctypes=[dt("Purchase Receipt", TRANSACTION, is_return=0)],
        reports=["Purchase Receipt Trends", "Received Items To Be Billed"],
    ),
    feature(
        "procurement.purchase_invoice", "Purchase Invoices",
        doctypes=[dt("Purchase Invoice", TRANSACTION, is_return=0)],
        reports=["Purchase Register", "Item-wise Purchase Register", "Purchase Invoice Trends",
                 "Billed Items To Be Received"],
        api_prefixes=[API + "purchase_invoices."],
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "procurement.purchase_return", "Purchase Returns (debit notes)",
        doctypes=[dt("Purchase Invoice", TRANSACTION, is_return=1), dt("Purchase Receipt", TRANSACTION, is_return=1)],
        requires={"procurement.purchase_invoice": ["read"]},
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "procurement.analytics", "Purchase analytics",
        reports=["Purchase Analytics", "Item-wise Purchase History"],
    ),
    feature(
        "procurement.settings", "Buying settings",
        doctypes=[dt("Buying Settings", SETTINGS)],
    ),
]
