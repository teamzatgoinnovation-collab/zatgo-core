"""Which tax template a server-built sale uses: never a guess, and never a silent sale without the tax that applies."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.services import vansalex_settings
from zatgo_core.services.vansalex_service import _apply_sales_taxes


class TestSalesTaxTemplate(IntegrationTestCase):
    """Own company per test, so templates of other suites don't matter."""

    def setUp(self) -> None:
        abbr = f"T{random_string(5).upper()}"
        self.company = f"ZatGo Tax Test {abbr}"
        frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": self.company,
                "abbr": abbr,
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True)
        self.account = frappe.db.get_value("Account", {"company": self.company, "is_group": 0, "root_type": "Liability"}, "name")

    def _template(self, title: str, is_default: int = 0) -> str:
        return (
            frappe.get_doc(
                {
                    "doctype": "Sales Taxes and Charges Template",
                    "title": title,
                    "company": self.company,
                    "is_default": is_default,
                    "taxes": [{"charge_type": "On Net Total", "account_head": self.account, "description": "VAT", "rate": 15}],
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def test_no_template_means_no_tax(self) -> None:
        self.assertEqual(vansalex_settings.sales_tax_template(self.company), (None, False))

    def test_the_only_template_is_used(self) -> None:
        only = self._template("Only")
        self.assertEqual(vansalex_settings.sales_tax_template(self.company)[0], only)

    def test_the_default_wins_over_others(self) -> None:
        self._template("Other")
        default = self._template("Standard", is_default=1)
        self.assertEqual(vansalex_settings.sales_tax_template(self.company)[0], default)

    def test_several_without_a_default_are_refused(self) -> None:
        self._template("Zero rated")
        self._template("Standard")
        with self.assertRaises(frappe.ValidationError) as ctx:
            vansalex_settings.sales_tax_template(self.company)
        self.assertIn("none is the default", str(ctx.exception))
        # The app's read of the same setting keeps working, or it could not even open.
        self.assertEqual(vansalex_settings.tax_summary(self.company)["tax_template"], None)

    def test_a_chosen_template_that_is_gone_is_refused(self) -> None:
        with patch.object(
            vansalex_settings,
            "_zg_company_setting",
            side_effect=lambda company, field: "Deleted Template" if field == "default_tax_template" else 0,
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                vansalex_settings.sales_tax_template(self.company)
        self.assertIn("no longer exists", str(ctx.exception))

    def test_failure_to_apply_the_template_stops_the_sale(self) -> None:
        self._template("Standard", is_default=1)
        doc = frappe.get_doc({"doctype": "Sales Invoice", "company": self.company})
        with (
            patch("erpnext.controllers.accounts_controller.get_taxes_and_charges", side_effect=RuntimeError("boom")),
            patch.object(type(doc), "append_taxes_from_master", side_effect=RuntimeError("boom")),
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                _apply_sales_taxes(doc, self.company)
        self.assertIn("Nothing was recorded", str(ctx.exception))

    def test_template_rows_reach_the_invoice(self) -> None:
        self._template("Standard", is_default=1)
        doc = frappe.get_doc({"doctype": "Sales Invoice", "company": self.company})
        _apply_sales_taxes(doc, self.company)
        self.assertEqual([round(t.rate) for t in doc.taxes], [15])
