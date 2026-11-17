"""Sales: customers, quotations, orders, invoices, returns, deliveries, pricing."""

from zatgo_core.licensing.registry import MASTER, SETTINGS, TRANSACTION, Module, dt, feature

MODULE = Module(id="sales", label="Sales", category="Business", order=20, icon="sell",
                description="Customers, quotations, sales orders, invoices, returns and deliveries.")

API = "zatgo_core.api.v1.accounting."

FEATURES = [
    feature(
        "sales.customers", "Customers",
        doctypes=[dt("Customer", MASTER), dt("Customer Group", MASTER)],
        reports=["Customer Credit Balance", "Inactive Customers", "Customers Without Any Sales Transactions",
                 "Customer Acquisition and Loyalty", "Address And Contacts"],
        api_prefixes=[API + "customers."],
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "sales.quotation", "Quotations",
        doctypes=[dt("Quotation", TRANSACTION)],
        reports=["Quotation Trends", "Lost Quotations"],
        api_prefixes=[API + "quotations."],
        platforms=["desk", "desktop"],
    ),
    feature(
        "sales.order", "Sales Orders",
        doctypes=[dt("Sales Order", TRANSACTION)],
        reports=["Sales Order Analysis", "Sales Order Trends", "Payment Terms Status for Sales Order",
                 "Delayed Order Report"],
        workspaces=["Selling"],
    ),
    feature(
        "sales.invoice", "Sales Invoices",
        description="Sales Invoices that are not returns (cash and credit alike; ERPNext posts the GL).",
        doctypes=[dt("Sales Invoice", TRANSACTION, is_return=0)],
        reports=["Sales Register", "Item-wise Sales Register", "Sales Invoice Trends", "Sales Payment Summary",
                 "Gross Profit", "Item-wise Sales History"],
        workspaces=["Invoicing", "Selling"],
        api_prefixes=[API + "invoices."],
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "sales.return", "Sales Returns (credit notes)",
        description="Sales Invoices and Delivery Notes with is_return = 1.",
        doctypes=[dt("Sales Invoice", TRANSACTION, is_return=1), dt("Delivery Note", TRANSACTION, is_return=1)],
        requires={"sales.invoice": ["read"]},
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "sales.delivery_note", "Delivery Notes",
        doctypes=[dt("Delivery Note", TRANSACTION, is_return=0)],
        reports=["Delivery Note Trends", "Delivered Items To Be Billed"],
    ),
    feature(
        "sales.pricing", "Pricing rules and price lists",
        doctypes=[dt("Item Price", MASTER), dt("Pricing Rule", MASTER), dt("Promotional Scheme", MASTER),
                  dt("Coupon Code", MASTER), dt("Product Bundle", MASTER)],
        reports=["Item Prices", "Item-wise Price List Rate", "Customer-wise Item Price"],
    ),
    feature(
        "sales.team", "Sales team and partners",
        doctypes=[dt("Sales Person", MASTER), dt("Sales Partner", MASTER)],
        reports=["Sales Person-wise Transaction Summary", "Sales Partners Commission",
                 "Sales Person Commission Summary", "Sales Partner Commission Summary",
                 "Sales Partner Transaction Summary", "Territory-wise Sales",
                 "Sales Person Target Variance Based On Item Group", "Territory Target Variance Based On Item Group",
                 "Sales Partner Target Variance based on Item Group"],
    ),
    feature(
        "sales.analytics", "Sales analytics",
        reports=["Sales Analytics", "Inactive Sales Items"],
    ),
    feature(
        "sales.settings", "Selling settings",
        doctypes=[dt("Selling Settings", SETTINGS)],
    ),
]

