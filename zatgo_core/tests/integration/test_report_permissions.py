"""ZatGo Script Reports read raw SQL, so they check the company filter themselves (Phase 10)."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string, today

from zatgo_core.zatgo_core.report.business_summary_report import business_summary_report
from zatgo_core.zatgo_core.report.payment_method_summary import payment_method_summary

REPORTS = (business_summary_report, payment_method_summary)


class TestReportPermissions(IntegrationTestCase):
    def setUp(self) -> None:
        companies = frappe.get_all("Company", pluck="name", limit=2)
        if len(companies) < 2:
            self.skipTest("needs two companies")
        self.mine, self.other = companies
        self.email = f"zg-report-{random_string(6).lower()}@example.test"
        frappe.get_doc({"doctype": "User", "email": self.email, "first_name": "r", "send_welcome_email": 0,
                        "roles": [{"role": "Accounts User"}]}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "User Permission", "user": self.email, "allow": "Company", "for_value": self.mine,
                        "apply_to_all_doctypes": 1}).insert(ignore_permissions=True)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.delete_doc("User", self.email, force=True, ignore_permissions=True)

    def _run(self, report, company: str):
        return report.execute({"company": company, "from_date": today(), "to_date": today()})

    def test_a_user_reads_their_company(self) -> None:
        frappe.set_user(self.email)
        for report in REPORTS:
            self.assertTrue(self._run(report, self.mine), report.__name__)

    def test_a_user_cannot_read_another_company(self) -> None:
        frappe.set_user(self.email)
        for report in REPORTS:
            with self.assertRaises(frappe.PermissionError, msg=report.__name__):
                self._run(report, self.other)
