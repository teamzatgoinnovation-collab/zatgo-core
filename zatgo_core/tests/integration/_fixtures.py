"""Shared, deterministic fixtures for zatgo_core integration tests.

On the shared dev bench, other apps' test suites (e.g. zatca_integration)
create their own throwaway Company records. An unfiltered/unordered
`frappe.db.get_value("Company", {}, "name")` can pick one of those up
instead of a company these tests actually control, silently assuming
whatever currency/country that company happens to have. Use
`get_or_create_test_company()` instead of querying "any Company".
"""

from __future__ import annotations

import frappe

TEST_COMPANY_NAME = "ZatGo Core Test Co"
TEST_COMPANY_ABBR = "ZCTC"


def get_or_create_test_company() -> str:
    if not frappe.db.exists("Company", TEST_COMPANY_NAME):
        frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": TEST_COMPANY_NAME,
                "abbr": TEST_COMPANY_ABBR,
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True)
    return TEST_COMPANY_NAME


def get_or_create_cash_mode_of_payment(company: str, cash_account: str) -> str:
    """"Cash" is a standard setup-wizard fixture that a bare `bench new-site
    --install-app erpnext` (skipping the wizard) never creates -- see
    erpnext/CLAUDE.md. Real, wizard-provisioned sites already have it; this
    just makes the test suite not depend on which kind of site it runs
    against."""
    if not frappe.db.exists("Mode of Payment", "Cash"):
        frappe.get_doc(
            {
                "doctype": "Mode of Payment",
                "mode_of_payment": "Cash",
                "type": "Cash",
                "accounts": [{"company": company, "default_account": cash_account}],
            }
        ).insert(ignore_permissions=True)
    elif not frappe.db.exists(
        "Mode of Payment Account", {"parent": "Cash", "company": company}
    ):
        mop = frappe.get_doc("Mode of Payment", "Cash")
        mop.append("accounts", {"company": company, "default_account": cash_account})
        mop.save(ignore_permissions=True)
    return "Cash"
