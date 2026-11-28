"""Phase 9 business rules: API invoices carry the company's tax template (T-01), a quotation is invoiced once
(S-01), and a replayed client_id never acknowledges a cancelled, unfinished or different document (S-02)."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.services import invoice_taxes
from zatgo_core.services.vansalex_service import _replayable


class TestInvoiceTaxes(IntegrationTestCase):
    def setUp(self) -> None:
        abbr = f"P{random_string(5).upper()}"
        self.company = f"ZatGo Phase9 {abbr}"
        frappe.get_doc({"doctype": "Company", "company_name": self.company, "abbr": abbr,
                        "default_currency": "SAR", "country": "Saudi Arabia"}).insert(ignore_permissions=True)
        self.account = frappe.db.get_value("Account", {"company": self.company, "is_group": 0, "root_type": "Liability"}, "name")

    def _template(self, master: str, is_default: int = 1) -> str:
        child = {"charge_type": "On Net Total", "account_head": self.account, "description": "VAT", "rate": 15}
        if master.startswith("Purchase"):
            child["category"] = "Total"
            child["add_deduct_tax"] = "Add"
        return frappe.get_doc({"doctype": master, "title": f"VAT {random_string(4)}", "company": self.company,
                               "is_default": is_default, "taxes": [child]}).insert(ignore_permissions=True).name

    def test_api_sales_invoice_gets_the_company_template(self) -> None:
        template = self._template("Sales Taxes and Charges Template")
        doc = frappe.get_doc({"doctype": "Sales Invoice", "company": self.company})
        invoice_taxes.apply_if_unset(doc, self.company)
        self.assertEqual(doc.taxes_and_charges, template)
        self.assertEqual([round(t.rate) for t in doc.taxes], [15])

    def test_api_purchase_invoice_gets_the_default_template(self) -> None:
        template = self._template("Purchase Taxes and Charges Template")
        doc = frappe.get_doc({"doctype": "Purchase Invoice", "company": self.company})
        invoice_taxes.apply_if_unset(doc, self.company)
        self.assertEqual(doc.taxes_and_charges, template)
        self.assertEqual(len(doc.taxes), 1)

    def test_purchase_without_a_default_template_gets_none(self) -> None:
        self._template("Purchase Taxes and Charges Template", is_default=0)
        doc = frappe.get_doc({"doctype": "Purchase Invoice", "company": self.company})
        invoice_taxes.apply_if_unset(doc, self.company)
        self.assertFalse(doc.taxes)

    def test_a_template_the_caller_chose_is_kept(self) -> None:
        self._template("Sales Taxes and Charges Template")
        doc = frappe.get_doc({"doctype": "Sales Invoice", "company": self.company, "taxes_and_charges": "Mine"})
        invoice_taxes.apply_if_unset(doc, self.company)
        self.assertEqual(doc.taxes_and_charges, "Mine")
        self.assertFalse(doc.taxes)

    def test_the_create_path_applies_taxes_before_insert(self) -> None:
        from zatgo_core.services import erpnext_writes

        seen = {}

        def fake_insert(doc, *, doctype, client_id):
            seen["taxes"] = doc.taxes_and_charges
            raise RuntimeError("stop before writing")

        template = self._template("Sales Taxes and Charges Template")
        with (
            patch("zatgo_core.services.erpnext_writes._parse_items", return_value=[]),
            patch("zatgo_core.services.idempotency.insert_idempotent", side_effect=fake_insert),
        ):
            with self.assertRaises(RuntimeError):
                erpnext_writes.create_sales_invoice(customer="any", items=[], company=self.company,
                                                    client_id=random_string(10))
        self.assertEqual(seen["taxes"], template)


class TestQuotationInvoicedOnce(IntegrationTestCase):
    def test_a_second_conversion_returns_the_first_invoice(self) -> None:
        from zatgo_core.services import erpnext_writes

        existing = frappe.get_all("Sales Invoice", filters={"docstatus": ["<", 2]}, pluck="name", limit=1)
        quotation = frappe.get_all("Quotation", filters={"docstatus": 1}, pluck="name", limit=1)
        if not existing or not quotation:
            self.skipTest("needs a submitted Quotation and a Sales Invoice")
        with (
            patch("zatgo_core.services.idempotency.find_by_client_id", return_value=existing[0]),
            patch("zatgo_core.services.core.erpnext_api.make_sales_invoice_from_quotation") as mapper,
        ):
            result = erpnext_writes.create_sales_invoice_from_quotation(quotation[0])
        mapper.assert_not_called()
        self.assertTrue(result["meta"]["idempotent"])


class TestReplays(IntegrationTestCase):
    def _doc(self, docstatus: int):
        return frappe._dict(doctype="Stock Entry", name="SE-X", docstatus=docstatus)

    def test_a_cancelled_document_is_not_acknowledged(self) -> None:
        with self.assertRaises(frappe.ValidationError) as ctx:
            _replayable(self._doc(2))
        self.assertIn("cancelled", str(ctx.exception))

    def test_an_unfinished_document_is_not_acknowledged(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            _replayable(self._doc(0))
        self.assertEqual(_replayable(self._doc(0), allow_draft=True).name, "SE-X")

    def test_a_submitted_document_is_acknowledged(self) -> None:
        self.assertEqual(_replayable(self._doc(1)).name, "SE-X")
