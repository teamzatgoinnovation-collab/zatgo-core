"""Tax: templates, VAT reports, withholding, ZATCA e-invoicing.

India GST is not registered (no india_compliance on this product, decision D7). The ZATCA Phase 1 QR on
zatgo_core's print formats is a legal requirement of every KSA invoice and is never gated. The ZATCA records
made on submit (ZATCA Invoice, ZATCA Submission Log) are in NEVER_GATE; only the app's setup is licensed."""

from zatgo_core.licensing.registry import MASTER, SETTINGS, Module, dt, feature

MODULE = Module(id="tax", label="Tax Management", category="Business", order=55, icon="tax",
                description="Tax templates and rules, VAT reports, withholding, ZATCA e-invoicing.")

FEATURES = [
    feature(
        "tax.templates", "Tax templates and rules",
        doctypes=[dt("Sales Taxes and Charges Template", MASTER), dt("Purchase Taxes and Charges Template", MASTER),
                  dt("Item Tax Template", MASTER), dt("Tax Category", MASTER), dt("Tax Rule", MASTER)],
    ),
    feature(
        "tax.vat_reports", "VAT reports",
        reports=["VAT Audit Report", "UAE VAT 201"],
    ),
    feature(
        "tax.withholding", "Tax withholding",
        doctypes=[dt("Tax Withholding Category", MASTER)],
        reports=["Tax Withholding Details", "TDS Computation Summary"],
    ),
    feature(
        "tax.zatca", "ZATCA e-invoicing",
        doctypes=[dt("ZATCA Settings", SETTINGS), dt("ZATCA EGS", MASTER), dt("ZATCA Tax Category", MASTER)],
        reports=["ZATCA Status Report", "ZATCA Sales Invoices with Warnings"],
        workspaces=["ZATCA Integration"],
        source_app="zatca_integration",
    ),
]

