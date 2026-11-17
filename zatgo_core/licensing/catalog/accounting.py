"""Finance & accounting: chart, journals, payments, ledgers, receivables/payables, bank, statements.

GL Entry / Payment Ledger Entry are never gated (NEVER_GATE); the ledgers are read through the reports here.
There is no separate "Cash Book" / "Bank Book" in ERPNext: the General Ledger filtered on a cash or bank
account is that book, so they are not registered as features of their own."""

from zatgo_core.licensing.registry import MASTER, SETTINGS, TRANSACTION, Module, dt, feature

MODULE = Module(id="accounting", label="Finance and Accounting", category="Business", order=50,
                icon="accounting",
                description="Chart of accounts, journals, payments, ledgers, bank and financial statements.")

API = "zatgo_core.api.v1.accounting."

FEATURES = [
    feature(
        "accounting.chart_of_accounts", "Chart of accounts and cost centers",
        doctypes=[dt("Account", MASTER), dt("Cost Center", MASTER), dt("Accounting Dimension", MASTER),
                  dt("Finance Book", MASTER)],
        api_prefixes=[API + "accounts."],
        platforms=["desk", "desktop"],
    ),
    feature(
        "accounting.journal_entry", "Journal Entries",
        doctypes=[dt("Journal Entry", TRANSACTION), dt("Journal Entry Template", MASTER)],
        workspaces=["Invoicing"],
        api_prefixes=[API + "journals."],
        platforms=["desk", "desktop"],
    ),
    feature(
        "accounting.payment_entry", "Payment Entries",
        doctypes=[dt("Payment Entry", TRANSACTION), dt("Payment Request", TRANSACTION),
                  dt("Payment Reconciliation", SETTINGS)],
        reports=["Payment Method Summary", "Payment Period Based On Invoice Date"],
        api_prefixes=[API + "payments.", API + "payment_methods."],
        platforms=["desk", "desktop", "mobile"],
    ),
    feature(
        "accounting.ledgers", "General ledger and trial balance",
        reports=["General Ledger", "Trial Balance", "Trial Balance (Simple)", "Trial Balance for Party",
                 "Account Balance", "Payment Ledger", "Voucher-wise Balance"],
        api_prefixes=[API + "reports."],
        platforms=["desk", "desktop"],
    ),
    feature(
        "accounting.receivables", "Accounts receivable",
        reports=["Accounts Receivable", "Accounts Receivable Summary", "Customer Ledger Summary"],
        platforms=["desk", "desktop"],
    ),
    feature(
        "accounting.payables", "Accounts payable",
        reports=["Accounts Payable", "Accounts Payable Summary", "Supplier Ledger Summary"],
        platforms=["desk", "desktop"],
    ),
    feature(
        "accounting.bank", "Bank accounts and reconciliation",
        doctypes=[dt("Bank", MASTER), dt("Bank Account", MASTER), dt("Bank Transaction", TRANSACTION),
                  dt("Bank Reconciliation Tool", SETTINGS)],
        reports=["Bank Reconciliation Statement", "Bank Clearance Summary",
                 "Cheques and Deposits Incorrectly cleared"],
    ),
    feature(
        "accounting.financial_statements", "Financial statements",
        reports=["Balance Sheet", "Profit and Loss Statement", "Cash Flow", "Financial Ratios",
                 "Consolidated Financial Statement", "Consolidated Trial Balance", "Gross and Net Profit Report",
                 "Profitability Analysis", "Dimension-wise Accounts Balance Report", "Custom Financial Statement"],
        workspaces=["Financial Reports"],
        platforms=["desk", "desktop"],
    ),
    feature(
        "accounting.budget", "Budgets",
        doctypes=[dt("Budget", TRANSACTION)],
        reports=["Budget Variance Report"],
    ),
    feature(
        "accounting.period_closing", "Period closing",
        doctypes=[dt("Period Closing Voucher", TRANSACTION), dt("Accounting Period", MASTER)],
    ),
    feature(
        "accounting.settings", "Accounts settings",
        doctypes=[dt("Accounts Settings", SETTINGS)],
    ),
]
