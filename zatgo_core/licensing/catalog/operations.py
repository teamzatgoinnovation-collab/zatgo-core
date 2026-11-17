"""CRM, production, quality and service: ERPNext's own modules for them, registered as they ship.

Only ERPNext's CRM module is registered here; the separate Frappe CRM app (`crm`) is not part of the product."""

from zatgo_core.licensing.registry import MASTER, SETTINGS, TRANSACTION, Module, dt, feature

# This file holds four modules; the loader reads MODULES when a file defines it.
MODULES = [
    Module(id="crm", label="CRM", category="Business", order=15, icon="crm",
           description="Leads, opportunities, appointments, contracts and campaigns."),
    Module(id="production", label="Production", category="Business", order=60, icon="organization",
           description="BOMs, work orders, job cards, workstations and production planning."),
    Module(id="quality", label="Quality", category="Business", order=65, icon="quality",
           description="Quality inspections, goals, procedures, reviews and actions."),
    Module(id="service", label="Service", category="Business", order=75, icon="support",
           description="Issues, warranty claims and maintenance."),
]
MODULE = MODULES[0]

MANUFACTURE_PURPOSES = ("Manufacture", "Material Transfer for Manufacture", "Material Consumption for Manufacture")

FEATURES = [
    # -- CRM
    feature(
        "crm.leads", "Leads and prospects",
        doctypes=[dt("Lead", MASTER), dt("Prospect", MASTER)],
        reports=["Lead Details", "Lead Conversion Time", "Lead Owner Efficiency",
                 "Prospects Engaged But Not Converted"],
        workspaces=["CRM"],
        api_prefixes=["zatgo_core.api.v1.crm.leads."],
    ),
    feature(
        "crm.opportunities", "Opportunities",
        doctypes=[dt("Opportunity", MASTER)],
        reports=["Opportunity Summary by Sales Stage", "Lost Opportunity", "Sales Pipeline Analytics",
                 "First Response Time for Opportunity"],
        pages=["sales-funnel"],
    ),
    feature(
        "crm.activities", "Appointments and contracts",
        doctypes=[dt("Appointment", MASTER), dt("Contract", TRANSACTION)],
    ),
    feature(
        "crm.campaigns", "Campaigns",
        doctypes=[dt("Campaign", MASTER), dt("Email Campaign", MASTER)],
        reports=["Campaign Efficiency"],
    ),
    # -- Production
    feature(
        "production.bom", "Bills of materials",
        doctypes=[dt("BOM", TRANSACTION)],
        reports=["BOM Explorer", "BOM Search", "BOM Stock Analysis", "BOM Variance Report", "BOM Operations Time"],
        pages=["bom-comparison-tool"],
    ),
    feature(
        "production.work_order", "Work orders and manufacturing stock entries",
        doctypes=[dt("Work Order", TRANSACTION), dt("Stock Entry", TRANSACTION, purpose=MANUFACTURE_PURPOSES)],
        reports=["Work Order Summary", "Open Work Orders", "Completed Work Orders", "Work Orders in Progress",
                 "Production Analytics", "Work Order Stock Report", "Work Order Consumed Materials",
                 "Issued Items Against Work Order", "Process Loss Report"],
        workspaces=["Manufacturing"],
        requires={"production.bom": ["read"]},
    ),
    feature(
        "production.job_card", "Job cards and workstations",
        doctypes=[dt("Job Card", TRANSACTION), dt("Workstation", MASTER), dt("Operation", MASTER),
                  dt("Routing", MASTER)],
        reports=["Job Card Summary", "Downtime Analysis"],
        pages=["visual-plant-floor"],
        requires={"production.work_order": ["read"]},
    ),
    feature(
        "production.planning", "Production planning",
        doctypes=[dt("Production Plan", TRANSACTION)],
        reports=["Production Plan Summary", "Production Planning Report", "Material Requirements Planning Report"],
        requires={"production.work_order": ["read", "create"]},
    ),
    feature(
        "production.settings", "Manufacturing settings",
        doctypes=[dt("Manufacturing Settings", SETTINGS)],
    ),
    # -- Quality
    feature(
        "quality.inspection", "Quality inspections",
        doctypes=[dt("Quality Inspection", TRANSACTION), dt("Quality Inspection Template", MASTER)],
        reports=["Quality Inspection Summary", "Cost of Poor Quality Report"],
    ),
    feature(
        "quality.management", "Quality goals, procedures and reviews",
        doctypes=[dt(name, MASTER) for name in ("Quality Goal", "Quality Procedure", "Quality Review",
                                                "Quality Action", "Non Conformance", "Quality Feedback",
                                                "Quality Meeting")],
        workspaces=["Quality"],
    ),
    # -- Service
    feature(
        "service.issue", "Issues and SLAs",
        doctypes=[dt("Issue", MASTER), dt("Issue Type", MASTER), dt("Issue Priority", MASTER),
                  dt("Service Level Agreement", MASTER)],
        reports=["Issue Analytics", "Issue Summary", "First Response Time for Issues", "Support Hour Distribution"],
        workspaces=["Support"],
    ),
    feature(
        "service.warranty", "Warranty claims",
        doctypes=[dt("Warranty Claim", MASTER)],
        reports=["Serial No Warranty Expiry", "Serial No Service Contract Expiry"],
    ),
    feature(
        "service.maintenance", "Maintenance schedules and visits",
        doctypes=[dt("Maintenance Schedule", TRANSACTION), dt("Maintenance Visit", TRANSACTION)],
        reports=["Maintenance Schedules"],
    ),
    feature(
        "service.field_tickets", "Field service tickets",
        description="ZatGo's own field service tickets (ZG Service Ticket) and their API.",
        doctypes=[dt("ZG Service Ticket", MASTER)],
        api_prefixes=["zatgo_core.api.v1.service."],
        source_app="zatgo_core",
        platforms=["desk", "mobile"],
    ),
]
