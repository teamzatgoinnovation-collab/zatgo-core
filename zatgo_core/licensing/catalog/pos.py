"""POS: ERPNext's point of sale and the ZatGo POS desktop app.

The ZatGo POS app posts Sales Invoices + Payment Entries (not POS Invoices), so it needs those features --
declared in `requires`, never added silently: a POS edition must include them itself."""

from zatgo_core.licensing.registry import MASTER, TRANSACTION, Module, dt, feature

MODULE = Module(id="pos", label="POS", category="Business", order=70, icon="pos",
                description="POS profiles, invoices, cash sessions and the ZatGo POS app.")

FEATURES = [
    feature(
        "pos.profile", "POS profiles",
        doctypes=[dt("POS Profile", MASTER)],
        api_prefixes=["zatgo_core.api.v1.pos_profile."],
        platforms=["desk", "desktop"],
    ),
    feature(
        "pos.invoice", "ERPNext point of sale (POS Invoice)",
        doctypes=[dt("POS Invoice", TRANSACTION)],
        reports=["POS Register"],
        pages=["point-of-sale"],
        requires={"pos.profile": ["read"], "pos.session": ["create", "submit"]},
    ),
    feature(
        "pos.session", "Cash sessions (opening / closing)",
        doctypes=[dt("POS Opening Entry", TRANSACTION), dt("POS Closing Entry", TRANSACTION)],
        platforms=["desk", "desktop"],
    ),
    feature(
        "pos.zatgo_pos", "ZatGo POS app",
        description="The desktop POS (retail; restaurant needs the Restaurant industry too).",
        workspaces=["ZatGo POS"],
        api_prefixes=["zatgo_core.api.v1.retail_pos.", "zatgo_core.api.v1.pos_settings."],
        app_key="zatgo_pos",
        source_app="zatgo_core",
        platforms=["desk", "desktop"],
        requires={
            "pos.profile": ["read"],
            "pos.session": ["create", "submit"],
            "sales.invoice": ["create", "submit"],
            "accounting.payment_entry": ["create", "submit"],
        },
    ),
]
