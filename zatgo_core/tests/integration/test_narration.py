"""Narration on every transaction (patches/v0_2_5/add_narration_fields.py,
services/narration.py).

Real documents through real save/submit: a narration the user writes on a
Payment Entry / Journal Entry survives ERPNext's own auto-remark logic and
reaches the GL; one left alone still follows ERPNext's auto-text.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import add_days, nowdate, random_string

from zatgo_core.patches.v0_2_5.add_narration_fields import NATIVE_NARRATION, NEW_NARRATION
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestNarration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.company = get_or_create_test_company()
        cls.cash = frappe.get_cached_value("Company", cls.company, "default_cash_account")
        cls.expense = frappe.db.get_value(
            "Account", {"company": cls.company, "root_type": "Expense", "is_group": 0}, "name"
        )
        cls.item_code = f"NARR-TEST-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": cls.item_code,
                "item_name": cls.item_code,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": 0,
            }
        ).insert(ignore_permissions=True)
        cls.customer = "Narration Test Customer"
        if not frappe.db.exists("Customer", cls.customer):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": cls.customer,
                    "customer_type": "Individual",
                    "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                    "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
                }
            ).insert(ignore_permissions=True)

    # -- helpers -------------------------------------------------------------

    def _credit_si(self, amount: float = 100):
        si = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "customer": self.customer,
                "company": self.company,
                "currency": "SAR",
                "conversion_rate": 1,
                "due_date": nowdate(),
                "custom_payment_type": "Credit",
                "items": [{"item_code": self.item_code, "qty": 1, "rate": amount}],
            }
        )
        si.insert(ignore_permissions=True)
        si.submit()
        return si

    def _draft_pe(self):
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

        pe = get_payment_entry("Sales Invoice", self._credit_si().name, bank_account=self.cash)
        pe.insert(ignore_permissions=True)
        return pe

    def _draft_je(self):
        je = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "company": self.company,
                "posting_date": nowdate(),
                # A cheque no. makes ERPNext auto-write a remark.
                "cheque_no": "CHQ-1",
                "cheque_date": nowdate(),
                "accounts": [
                    {"account": self.expense, "debit_in_account_currency": 50},
                    {"account": self.cash, "credit_in_account_currency": 50},
                ],
            }
        )
        je.insert(ignore_permissions=True)
        return je

    @staticmethod
    def _gl_remarks(voucher_no: str) -> set[str]:
        return set(
            frappe.get_all(
                "GL Entry", filters={"voucher_no": voucher_no, "is_cancelled": 0}, pluck="remarks"
            )
        )

    # -- fields ---------------------------------------------------------------

    def test_every_transaction_has_a_visible_narration(self) -> None:
        for doctype, (fieldname, section) in NATIVE_NARRATION.items():
            meta = frappe.get_meta(doctype)
            df = meta.get_field(fieldname)
            self.assertEqual(df.label, "Narration", doctype)
            self.assertFalse(df.hidden, doctype)
            self.assertFalse(meta.get_field(section).collapsible, f"{doctype} section collapsed")
        for doctype in ("Payment Entry", "Journal Entry"):
            field = NATIVE_NARRATION[doctype][0]
            self.assertFalse(frappe.get_meta(doctype).get_field(field).read_only_depends_on, doctype)
        for doctype in NEW_NARRATION:
            df = frappe.get_meta(doctype).get_field("custom_narration")
            self.assertIsNotNone(df, doctype)
            self.assertEqual(df.label, "Narration")
            self.assertTrue(
                frappe.db.has_column(doctype, "custom_narration"), f"{doctype}: column not created"
            )

    # -- Payment Entry --------------------------------------------------------

    def test_payment_entry_auto_text_when_left_alone(self) -> None:
        pe = self._draft_pe()
        self.assertFalse(pe.custom_remarks)
        self.assertIn("received from", pe.remarks)

    def test_payment_entry_narration_written_later_is_kept_and_posted(self) -> None:
        pe = self._draft_pe()
        pe.remarks = "Cash collected by driver Ahmed, receipt 4471"
        pe.save(ignore_permissions=True)
        self.assertEqual(pe.custom_remarks, 1)
        pe.reference_no = "R-1"  # another save must not bring the auto-text back
        pe.reference_date = nowdate()
        pe.save(ignore_permissions=True)
        pe.submit()
        self.assertEqual(
            frappe.db.get_value("Payment Entry", pe.name, "remarks"),
            "Cash collected by driver Ahmed, receipt 4471",
        )
        self.assertEqual(self._gl_remarks(pe.name), {"Cash collected by driver Ahmed, receipt 4471"})

    def test_payment_entry_cleared_narration_returns_to_auto_text(self) -> None:
        pe = self._draft_pe()
        pe.remarks = "temporary note"
        pe.save(ignore_permissions=True)
        pe.remarks = ""
        pe.save(ignore_permissions=True)
        self.assertEqual(pe.custom_remarks, 0)
        self.assertIn("received from", pe.remarks)

    def test_payment_entry_api_remarks_kept(self) -> None:
        from zatgo_core.services.erpnext_writes import create_receive_payment, update_payment_entry

        si = self._credit_si(80)
        data = create_receive_payment(sales_invoice=si.name, remarks="Paid at counter 2")["data"]
        self.assertEqual(data["narration"], "Paid at counter 2")
        name = data.get("name") or data.get("erp_name")
        self.assertEqual(frappe.db.get_value("Payment Entry", name, "remarks"), "Paid at counter 2")
        if frappe.db.get_value("Payment Entry", name, "docstatus") == 0:
            data = update_payment_entry(name, remarks="Paid at counter 3")["data"]
            self.assertEqual(data["narration"], "Paid at counter 3")

    # -- Journal Entry ----------------------------------------------------------

    def test_journal_entry_auto_text_when_left_alone(self) -> None:
        je = self._draft_je()
        self.assertFalse(je.custom_remark)
        self.assertIn("CHQ-1", je.remark)

    def test_journal_entry_narration_written_later_is_kept_and_posted(self) -> None:
        je = self._draft_je()
        je.remark = "Fuel for van 3, week 40"
        je.save(ignore_permissions=True)
        self.assertEqual(je.custom_remark, 1)
        je.cheque_no = "CHQ-2"
        je.save(ignore_permissions=True)
        je.submit()
        self.assertEqual(frappe.db.get_value("Journal Entry", je.name, "remark"), "Fuel for van 3, week 40")
        self.assertEqual(self._gl_remarks(je.name), {"Fuel for van 3, week 40"})

    def test_journal_entry_cleared_narration_returns_to_auto_text(self) -> None:
        je = self._draft_je()
        je.remark = "temporary"
        je.save(ignore_permissions=True)
        je.remark = ""
        je.save(ignore_permissions=True)
        self.assertEqual(je.custom_remark, 0)
        self.assertIn("CHQ-1", je.remark)

    # -- documents that had no narration ----------------------------------------

    def test_new_narration_field_saves(self) -> None:
        so = frappe.get_doc(
            {
                "doctype": "Sales Order",
                "customer": self.customer,
                "company": self.company,
                "transaction_date": nowdate(),
                "delivery_date": add_days(nowdate(), 1),
                "custom_narration": "Deliver before Friday prayers",
                "items": [{"item_code": self.item_code, "qty": 1, "rate": 10}],
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(
            frappe.db.get_value("Sales Order", so.name, "custom_narration"), "Deliver before Friday prayers"
        )

    def test_quotation_api_narration(self) -> None:
        from zatgo_core.services.erpnext_writes import create_quotation

        data = create_quotation(
            customer=self.customer,
            items=[{"item_code": self.item_code, "qty": 2, "rate": 5}],
            company=self.company,
            narration="Price valid for repeat orders",
        )["data"]
        self.assertEqual(data["narration"], "Price valid for repeat orders")
