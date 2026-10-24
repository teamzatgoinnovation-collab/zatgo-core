"""Business Summary Report: party payment / receipt / balance logic.

Each test measures the report before and after creating documents (deltas), so
it doesn't depend on whatever else the site already holds.
"""

from __future__ import annotations

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.party import get_party_account
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import nowdate, random_string

from zatgo_core.zatgo_core.report.business_summary_report.business_summary_report import execute
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestBusinessSummaryReport(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.cash_account = frappe.db.get_value(
            "Account", {"company": cls.company, "account_type": "Cash", "is_group": 0}, "name"
        )
        cls.item_code = cls._make_non_stock_item()
        cls.customer = cls._make_party("Customer", "BSR Test Customer")
        cls.supplier = cls._make_party("Supplier", "BSR Test Supplier")

    # -- fixtures ---------------------------------------------------------

    @classmethod
    def _make_non_stock_item(cls) -> str:
        code = f"BSR-TEST-{random_string(6).upper()}"
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
    def _make_party(cls, doctype: str, name: str) -> str:
        if frappe.db.exists(doctype, name):
            return name
        if doctype == "Customer":
            doc = {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Individual",
                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
            }
        else:
            doc = {
                "doctype": "Supplier",
                "supplier_name": name,
                "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
            }
        frappe.get_doc(doc).insert(ignore_permissions=True)
        return name

    def _invoice(self, doctype: str, amount: float):
        party_field = "customer" if doctype == "Sales Invoice" else "supplier"
        doc = frappe.get_doc(
            {
                "doctype": doctype,
                party_field: self.customer if doctype == "Sales Invoice" else self.supplier,
                "company": self.company,
                "currency": "SAR",
                "conversion_rate": 1,
                "posting_date": nowdate(),
                "due_date": nowdate(),
                "set_posting_time": 1,
                "items": [{"item_code": self.item_code, "qty": 1, "rate": amount}],
            }
        )
        doc.insert(ignore_permissions=True)
        doc.submit()
        return doc

    def _allocated_payment(self, invoice, amount: float):
        pe = get_payment_entry(invoice.doctype, invoice.name, party_amount=amount, bank_account=self.cash_account)
        pe.posting_date = nowdate()
        pe.reference_no = pe.reference_date = None
        pe.insert(ignore_permissions=True)
        pe.submit()
        return pe

    def _advance(self, party_type: str, payment_type: str, amount: float):
        """A Payment Entry with no invoice references, i.e. fully unallocated."""
        party = self.customer if party_type == "Customer" else self.supplier
        party_account = get_party_account(party_type, party, self.company)
        pay = payment_type == "Pay"
        pe = frappe.get_doc(
            {
                "doctype": "Payment Entry",
                "payment_type": payment_type,
                "company": self.company,
                "posting_date": nowdate(),
                "party_type": party_type,
                "party": party,
                "paid_from": self.cash_account if pay else party_account,
                "paid_to": party_account if pay else self.cash_account,
                "paid_amount": amount,
                "received_amount": amount,
                "source_exchange_rate": 1,
                "target_exchange_rate": 1,
            }
        )
        pe.insert(ignore_permissions=True)
        pe.submit()
        return pe

    @staticmethod
    def _cards(company: str) -> dict:
        today = nowdate()
        res = execute({"company": company, "from_date": today, "to_date": today})
        return {c["label"]: c["value"] for c in res[4]}

    # -- tests ------------------------------------------------------------

    def test_receipts_are_cash_received_net_of_refunds(self):
        before = self._cards(self.company)
        si = self._invoice("Sales Invoice", 100)
        self._allocated_payment(si, si.grand_total)
        self._advance("Customer", "Receive", 40)  # advance: counts, it is cash received
        self._advance("Customer", "Pay", 10)  # refund to the customer
        after = self._cards(self.company)
        d = lambda k: round(after[k] - before[k], 2)  # noqa: E731
        self.assertEqual(d("Sales Total"), round(si.base_net_total, 2))
        self.assertEqual(d("Party Receipt Total"), round(si.grand_total + 40 - 10, 2))

    def test_payments_are_cash_paid_net_of_refunds(self):
        before = self._cards(self.company)
        pi = self._invoice("Purchase Invoice", 200)
        self._allocated_payment(pi, 120)
        self._advance("Supplier", "Pay", 50)
        self._advance("Supplier", "Receive", 5)  # supplier refund
        after = self._cards(self.company)
        d = lambda k: round(after[k] - before[k], 2)  # noqa: E731
        self.assertEqual(d("Party Payment Total"), 165.0)
        self.assertEqual(d("Purchases Total"), round(pi.base_grand_total, 2))

    def test_purchases_net_of_return_and_reconcile_with_payments_and_payable(self):
        from erpnext.controllers.sales_and_purchase_return import make_return_doc

        before = self._cards(self.company)
        pi = self._invoice("Purchase Invoice", 200)
        ret = make_return_doc("Purchase Invoice", pi.name)
        ret.items[0].qty = -1  # return one unit of one
        ret.posting_date = nowdate()
        ret.set_posting_time = 1
        ret.insert(ignore_permissions=True)
        ret.submit()
        self._advance("Supplier", "Pay", 30)
        after = self._cards(self.company)
        d = lambda k: round(after[k] - before[k], 2)  # noqa: E731
        self.assertEqual(d("Purchases Total"), round(pi.base_grand_total + ret.base_grand_total, 2))
        # purchases - payable balance = payments (all of this run's cash is the 30 advance)
        self.assertEqual(
            round(d("Purchases Total") - d("Party Balance - Payable"), 2), d("Party Payment Total")
        )

    def test_balances_come_from_ledger_and_net_advances(self):
        before = self._cards(self.company)
        pi = self._invoice("Purchase Invoice", 200)
        self._allocated_payment(pi, 120)
        self._advance("Supplier", "Pay", 50)
        si = self._invoice("Sales Invoice", 100)
        self._advance("Customer", "Receive", 40)  # receipt not allocated: invoice stays outstanding
        after = self._cards(self.company)
        d = lambda k: round(after[k] - before[k], 2)  # noqa: E731
        # payable: 200 invoice - 120 allocated - 50 advance (invoice outstanding alone would say 80)
        self.assertEqual(d("Party Balance - Payable"), round(pi.base_grand_total - 170, 2))
        # receivable: invoice - 40 unallocated receipt
        self.assertEqual(d("Party Balance - Receivable"), round(si.base_grand_total - 40, 2))

    def test_unpermitted_user_cannot_read_company_figures(self):
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.PermissionError):
                self._cards(self.company)
        finally:
            frappe.set_user("Administrator")
