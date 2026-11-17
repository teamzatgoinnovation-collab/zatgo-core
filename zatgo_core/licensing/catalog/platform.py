"""Dashboards, custom reports, data import/export, print customisation."""

from zatgo_core.licensing.registry import MASTER, SETTINGS, Module, dt, feature

MODULES = [
    Module(id="dashboard", label="Dashboards", category="Analytics", order=10, icon="dashboard",
           source_app="frappe", description="Business dashboards, charts and number cards."),
    Module(id="reports", label="Reports and Analytics", category="Analytics", order=85, icon="table",
           source_app="frappe", description="Custom reports (Report Builder, query reports) and the BI API."),
    Module(id="data_management", label="Data Management", category="Administration", order=90, icon="upload",
           source_app="frappe", description="Data import and bulk export."),
    Module(id="print", label="Print and Documents", category="Administration", order=95, icon="printer",
           source_app="frappe", description="Print formats, print settings and printers."),
]
MODULE = MODULES[0]

FEATURES = [
    feature(
        "dashboard.business", "Business dashboards",
        doctypes=[dt("Dashboard", MASTER), dt("Dashboard Chart", MASTER), dt("Number Card", MASTER)],
        reports=["Business Summary Report"],
        pages=["dashboard-view"],
        api_prefixes=["zatgo_core.api.v1.accounting.dashboard."],
        source_app="frappe",
        platforms=["desk", "desktop"],
    ),
    feature(
        "reports.custom", "Custom reports",
        description="Creating and changing Report records (Report Builder and query reports). Running a "
        "report belongs to the feature that lists it.",
        doctypes=[dt("Report", MASTER)],
        source_app="frappe",
    ),
    feature(
        "reports.bi_api", "BI report API",
        api_prefixes=["zatgo_core.api.v1.bi."],
        source_app="zatgo_core",
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "data_management.import", "Data import",
        doctypes=[dt("Data Import", MASTER)],
        source_app="frappe",
    ),
    feature(
        "data_management.export", "Data export",
        doctypes=[dt("Data Export", SETTINGS)],
        source_app="frappe",
    ),
    feature(
        "print.formats", "Print format customisation",
        description="Designing print formats. Printing a document is the `print` action of its own feature.",
        doctypes=[dt("Print Format", MASTER), dt("Print Settings", SETTINGS)],
        pages=["print-format-builder", "print-format-builder-beta"],
        source_app="frappe",
    ),
    feature(
        "print.designer", "Print Designer",
        pages=["print-designer"],
        source_app="print_designer",
    ),
    feature(
        "print.printers", "ZatGo printer settings",
        doctypes=[dt("ZG Printer Settings", SETTINGS)],
        source_app="zatgo_core",
    ),
]
