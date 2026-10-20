"""IFRS Report Template switch (services/report_templates.py, overrides/query_report.py)."""

from __future__ import annotations

import json

import frappe
from frappe.desk.query_report import run as stock_run
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.overrides.query_report import run
from zatgo_core.services.report_templates import FIELD, SETTINGS, classic_filters

TEMPLATE = "Standard Balance Sheet (IFRS)"


def _set(value: int) -> None:
    doc = frappe.get_doc(SETTINGS)  # save through the doc so the cached single value is dropped, as the Desk does
    doc.set(FIELD, value)
    doc.save(ignore_permissions=True)


class TestReportTemplatesSwitch(IntegrationTestCase):
    def tearDown(self) -> None:
        _set(0)

    def test_classic_filters_drops_template_only_when_off(self) -> None:
        f = {"company": "X", "report_template": TEMPLATE}
        _set(0)
        self.assertEqual(classic_filters("Balance Sheet", f), {"company": "X"})
        self.assertEqual(json.loads(classic_filters("Balance Sheet", json.dumps(f))), {"company": "X"})
        self.assertEqual(classic_filters("Trial Balance", f), f)  # not a templated report
        _set(1)
        self.assertEqual(classic_filters("Balance Sheet", f), f)

    def test_run_is_classic_when_off_and_templated_when_on(self) -> None:
        if not frappe.db.exists("Financial Report Template", TEMPLATE):
            self.skipTest("ERPNext Financial Report Templates not available")
        company = frappe.db.get_value("GL Entry", {"is_cancelled": 0}, "company")
        fy = frappe.db.get_value("Fiscal Year", {}, "name", order_by="year_start_date desc")
        if not (company and fy):
            self.skipTest("no GL data")
        filters = {
            "company": company, "filter_based_on": "Fiscal Year", "from_fiscal_year": fy, "to_fiscal_year": fy,
            "periodicity": "Yearly", "report_template": TEMPLATE,
        }

        def templated(res) -> bool:
            return any(isinstance(r, dict) and "account_filters" in r for r in res["result"])

        frappe.set_user("Administrator")
        _set(0)
        self.assertFalse(templated(run("Balance Sheet", filters=dict(filters))))
        _set(1)
        self.assertTrue(templated(run("Balance Sheet", filters=dict(filters))))
        self.assertTrue(templated(stock_run("Balance Sheet", filters=dict(filters))))
