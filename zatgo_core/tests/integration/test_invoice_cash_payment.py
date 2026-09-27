"""Cash / Credit payment automation for Sales Invoice and Purchase Invoice.

Covers zatgo_core.services.invoice_cash_payment_service end-to-end through
real document submit/cancel (not the service function in isolation) so a
regression in the doc_events wiring in hooks.py is caught too, not just a
regression in the service logic.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)


class TestInvoiceCashPayment(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.cash_account = frappe.db.get_value(
            "Account",
            {"company": cls.company, "account_type": "Cash", "is_group": 0},
            "name",
        )
        get_or_create_cash_mode_of_payment(cls.company, cls.cash_account)
        cls.expense_account = frappe.db.get_value(
            "Account",
            {"company": cls.company, "account_type": "Expense Account", "is_group": 0},
            "name",
        )
        cls.item_code = cls._make_non_stock_item()
        cls.customer = cls._make_customer("Invoice Cash Payment Test Customer")
        cls.supplier = cls._make_supplier("Invoice Cash Payment Test Supplier")

    # -- fixtures -------------------------------------------------------

    @classmethod
    def _make_non_stock_item(cls) -> str:
        code = f"CASH-PAY-TEST-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": 0,
            }
        ).insert(ignore_permissions=True)
        return code

    @classmethod
    def _make_customer(cls, name: str) -> str:
        if frappe.db.exists("Customer", name):
            return name
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Individual",
                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
            }
        ).insert(ignore_permissions=True)
        return name

    @classmethod
    def _make_supplier(cls, name: str) -> str:
        if frappe.db.exists("Supplier", name):
            return name
        frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": name,
                "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
            }
        ).insert(ignore_permissions=True)
        return name

    def _make_sales_invoice(self, payment_type: str, cash_account: str | None = "keep") -> "frappe.model.document.Document":
        si = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": self.customer,
                "company": self.company,
                "currency": "SAR",
                "conversion_rate": 1,
                "due_date": frappe.utils.nowdate(),
                "custom_payment_type": payment_type,
                "custom_cash_account": self.cash_account if cash_account == "keep" else cash_account,
                "items": [{"item_code": self.item_code, "qty": 1, "rate": 100}],
            }
        )
        si.insert(ignore_permissions=True)
        return si

    def _make_purchase_invoice(
        self, payment_type: str, cash_account: str | None = "keep"
    ) -> "frappe.model.document.Document":
        pi = frappe.get_doc(
            {
                "doctype": "Purchase Invoice",
                "supplier": self.supplier,
                "company": self.company,
                "currency": "SAR",
                "conversion_rate": 1,
                "due_date": frappe.utils.nowdate(),
                "custom_payment_type": payment_type,
                "custom_cash_account": self.cash_account if cash_account == "keep" else cash_account,
                "items": [
                    {
                        "item_code": self.item_code,
                        "qty": 1,
                        "rate": 40,
                        "expense_account": self.expense_account,
                    }
                ],
            }
        )
        pi.insert(ignore_permissions=True)
        return pi

    @staticmethod
    def _linked_payment_entries(doctype: str, name: str, docstatus: int | None = 1) -> list[str]:
        filters = {"reference_doctype": doctype, "reference_name": name}
        if docstatus is not None:
            filters["docstatus"] = docstatus
        return frappe.get_all("Payment Entry Reference", filters=filters, pluck="parent")

    # -- Sales Invoice ----------------------------------------------------

    def test_sales_invoice_cash_auto_creates_and_submits_payment_entry(self) -> None:
        si = self._make_sales_invoice("Cash")
        si.submit()

        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 0)

        pe_names = self._linked_payment_entries("Sales Invoice", si.name)
        self.assertEqual(len(pe_names), 1)
        pe = frappe.db.get_value(
            "Payment Entry", pe_names[0], ["docstatus", "payment_type", "paid_to", "mode_of_payment"], as_dict=True
        )
        self.assertEqual(pe.docstatus, 1)
        self.assertEqual(pe.payment_type, "Receive")
        self.assertEqual(pe.paid_to, self.cash_account)
        self.assertEqual(pe.mode_of_payment, "Cash")

    def test_sales_invoice_cash_cancel_cascades_to_payment_entry(self) -> None:
        si = self._make_sales_invoice("Cash")
        si.submit()
        pe_name = self._linked_payment_entries("Sales Invoice", si.name)[0]

        si.reload()
        si.flags.ignore_permissions = True
        si.cancel()

        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "docstatus"), 2)
        self.assertEqual(frappe.db.get_value("Payment Entry", pe_name, "docstatus"), 2)

    def test_sales_invoice_credit_does_not_create_payment_entry(self) -> None:
        si = self._make_sales_invoice("Credit", cash_account=None)
        si.submit()

        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 100)
        self.assertEqual(self._linked_payment_entries("Sales Invoice", si.name, docstatus=None), [])

    def test_sales_invoice_cash_without_cash_account_blocks_submit(self) -> None:
        si = self._make_sales_invoice("Cash", cash_account=None)
        with self.assertRaises(frappe.ValidationError):
            si.submit()

    # -- Purchase Invoice ---------------------------------------------------

    def test_purchase_invoice_cash_auto_creates_and_submits_payment_entry(self) -> None:
        pi = self._make_purchase_invoice("Cash")
        pi.submit()

        self.assertEqual(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 0)

        pe_names = self._linked_payment_entries("Purchase Invoice", pi.name)
        self.assertEqual(len(pe_names), 1)
        pe = frappe.db.get_value(
            "Payment Entry", pe_names[0], ["docstatus", "payment_type", "paid_from", "mode_of_payment"], as_dict=True
        )
        self.assertEqual(pe.docstatus, 1)
        self.assertEqual(pe.payment_type, "Pay")
        self.assertEqual(pe.paid_from, self.cash_account)
        self.assertEqual(pe.mode_of_payment, "Cash")

    def test_purchase_invoice_cash_cancel_cascades_to_payment_entry(self) -> None:
        pi = self._make_purchase_invoice("Cash")
        pi.submit()
        pe_name = self._linked_payment_entries("Purchase Invoice", pi.name)[0]

        pi.reload()
        pi.flags.ignore_permissions = True
        pi.cancel()

        self.assertEqual(frappe.db.get_value("Purchase Invoice", pi.name, "docstatus"), 2)
        self.assertEqual(frappe.db.get_value("Payment Entry", pe_name, "docstatus"), 2)

    def test_purchase_invoice_credit_does_not_create_payment_entry(self) -> None:
        pi = self._make_purchase_invoice("Credit", cash_account=None)
        pi.submit()

        self.assertEqual(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 40)
        self.assertEqual(self._linked_payment_entries("Purchase Invoice", pi.name, docstatus=None), [])

    def test_purchase_invoice_cash_without_cash_account_blocks_submit(self) -> None:
        pi = self._make_purchase_invoice("Cash", cash_account=None)
        with self.assertRaises(frappe.ValidationError):
            pi.submit()
