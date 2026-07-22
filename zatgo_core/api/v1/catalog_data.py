"""Product API catalog for zatgo_core.api.v1.health.catalog.

Hub products only. Tracker (`tracker.api.v1.*`) and Chat AI (`chat_ai.api.*`)
are domain apps — they are intentionally omitted from this catalog.

Status values:
  active — full domain workflows on ZG DocTypes (or rich KDS/catalog)
  thin   — ERPNext-backed list/get (+ ping/status); clients may wire now
  stub   — placeholder helpers only
"""

PRODUCT_CATALOG = [
    {
        "product": "go_van",
        "title": "Go Van",
        "status": "thin",
        "namespace": "zatgo_core.api.v1.go_van",
        "hub": "zatgo_core.api.v1.go_van",
    },
    {
        "product": "delivery",
        "title": "Delivery",
        "status": "active",
        "namespace": "zatgo_core.api.v1.delivery",
        "hub": "zatgo_core.api.v1.delivery",
    },
    {
        "product": "resto_pos",
        "title": "ZatGo POS",
        "status": "active",
        "namespace": "zatgo_core.api.v1.resto_pos",
        "hub": "zatgo_core.api.v1.resto_pos",
    },
    {
        "product": "warehouse",
        "title": "Warehouse",
        "status": "thin",
        "namespace": "zatgo_core.api.v1.warehouse",
        "hub": "zatgo_core.api.v1.warehouse",
    },
    {
        "product": "crm",
        "title": "CRM",
        "status": "thin",
        "namespace": "zatgo_core.api.v1.crm",
        "hub": "zatgo_core.api.v1.crm",
    },
    {
        "product": "service",
        "title": "Field Service",
        "status": "thin",
        "namespace": "zatgo_core.api.v1.service",
        "hub": "zatgo_core.api.v1.service",
    },
    {
        "product": "hr",
        "title": "HR",
        "status": "thin",
        "namespace": "zatgo_core.api.v1.hr",
        "hub": "zatgo_core.api.v1.hr",
    },
    {
        "product": "fleet",
        "title": "Fleet",
        "status": "thin",
        "namespace": "zatgo_core.api.v1.fleet",
        "hub": "zatgo_core.api.v1.fleet",
    },
    {
        "product": "accounting",
        "title": "Accounting",
        "status": "active",
        "namespace": "zatgo_core.api.v1.accounting",
        "hub": "zatgo_core.api.v1.accounting",
    },
    {
        "product": "customer_portal",
        "title": "Customer Portal",
        "status": "stub",
        "namespace": "zatgo_core.api.v1.customer_portal",
        "hub": "zatgo_core.api.v1.customer_portal",
    },
    {
        "product": "vendor_portal",
        "title": "Vendor Portal",
        "status": "stub",
        "namespace": "zatgo_core.api.v1.vendor_portal",
        "hub": "zatgo_core.api.v1.vendor_portal",
    },
    {
        "product": "admin",
        "title": "Admin",
        "status": "thin",
        "namespace": "zatgo_core.api.v1.admin",
        "hub": "zatgo_core.api.v1.admin",
    },
    {
        "product": "bi",
        "title": "BI / Reports",
        "status": "thin",
        "namespace": "zatgo_core.api.v1.bi",
        "hub": "zatgo_core.api.v1.bi",
    },
    {
        "product": "documentation",
        "title": "Documentation",
        "status": "stub",
        "namespace": "zatgo_core.api.v1.documentation",
        "hub": "zatgo_core.api.v1.documentation",
    },
]
