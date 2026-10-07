"""Update/Delete coverage for transactional documents and master data.

The accounting-integrity rule this file guards: a submitted/posted document
can never be silently edited or deleted (see .claude/rules/accounting.md) —
only while still Draft (docstatus 0). Every `update_*`/`delete_*` added in
this phase must enforce that via `_require_draft`, and master-data delete
must surface ERPNext's own LinkExistsError rather than silently failing.
"""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.services.erpnext_writes import (
    _build_journal_entry_rows,
    create_customer,
    create_purchase_invoice,
    create_purchase_return,
    create_quotation,
    create_sales_invoice,
    create_sales_return,
    create_supplier,
    delete_account,
    delete_customer,
    delete_journal_entry,
    delete_purchase_invoice,
    delete_quotation,
    delete_sales_invoice,
    delete_supplier,
    submit_purchase_invoice,
    submit_sales_invoice,
    update_journal_entry,
    update_purchase_invoice,
    update_quotation,
    update_sales_invoice,
)
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class TestDocumentCrud(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        cls.item_code = f"CRUD-TEST-{random_string(6).upper()}"
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
        cls.customer = f"CRUD Test Customer {random_string(6)}"
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": cls.customer,
                "customer_type": "Individual",
                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
            }
        ).insert(ignore_permissions=True)
        cls.supplier = f"CRUD Test Supplier {random_string(6)}"
        frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": cls.supplier,
                "supplier_type": "Individual",
                "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
            }
        ).insert(ignore_permissions=True)

    def setUp(self) -> None:
        frappe.set_user("Administrator")

    def _items(self, rate: float = 10) -> list[dict]:
        return [{"item_code": self.item_code, "qty": 1, "rate": rate}]

    # -- Sales Invoice --------------------------------------------------

    def test_sales_invoice_update_and_delete_on_draft(self) -> None:
        created = create_sales_invoice(customer=self.customer, items=self._items(), company=self.company)
        name = created["data"]["name"]
        self.assertEqual(created["data"]["docstatus"], 0)

        updated = update_sales_invoice(name, remarks="edited by test")
        self.assertTrue(updated["success"], updated.get("error"))
        self.assertEqual(updated["data"]["remarks"], "edited by test")

        deleted = delete_sales_invoice(name)
        self.assertTrue(deleted["success"], deleted.get("error"))
        self.assertFalse(frappe.db.exists("Sales Invoice", name))

    def test_sales_invoice_update_and_delete_blocked_once_submitted(self) -> None:
        created = create_sales_invoice(customer=self.customer, items=self._items(), company=self.company)
        name = created["data"]["name"]
        submit_sales_invoice(name)
        self.assertEqual(frappe.db.get_value("Sales Invoice", name, "docstatus"), 1)

        with self.assertRaises(frappe.ValidationError):
            update_sales_invoice(name, remarks="should not apply")
        with self.assertRaises(frappe.ValidationError):
            delete_sales_invoice(name)
        self.assertTrue(frappe.db.exists("Sales Invoice", name))

    # -- Purchase Invoice (also exercises the map_purchase_invoice_doc docstatus fix) --

    def test_purchase_invoice_update_and_delete_on_draft(self) -> None:
        created = create_purchase_invoice(supplier=self.supplier, items=self._items(), company=self.company)
        name = created["data"]["name"]
        # Regression guard: map_purchase_invoice_doc previously never set docstatus,
        # which left BillDetailPage's docstatus-gated buttons permanently hidden.
        self.assertEqual(created["data"]["docstatus"], 0)

        updated = update_purchase_invoice(name, remarks="edited bill")
        self.assertTrue(updated["success"], updated.get("error"))
        self.assertEqual(updated["data"]["docstatus"], 0)
        self.assertEqual(updated["data"]["remarks"], "edited bill")

        deleted = delete_purchase_invoice(name)
        self.assertTrue(deleted["success"], deleted.get("error"))
        self.assertFalse(frappe.db.exists("Purchase Invoice", name))

    def test_purchase_invoice_update_and_delete_blocked_once_submitted(self) -> None:
        created = create_purchase_invoice(supplier=self.supplier, items=self._items(), company=self.company)
        name = created["data"]["name"]
        submit_purchase_invoice(name)
        self.assertEqual(frappe.db.get_value("Purchase Invoice", name, "docstatus"), 1)

        with self.assertRaises(frappe.ValidationError):
            update_purchase_invoice(name, remarks="should not apply")
        with self.assertRaises(frappe.ValidationError):
            delete_purchase_invoice(name)

    # -- Returns: one item on two lines -----------------------------------

    def _two_line_items(self) -> list[dict]:
        return [
            {"item_code": self.item_code, "qty": 2, "rate": 10},
            {"item_code": self.item_code, "qty": 5, "rate": 10},
        ]

    def test_sales_return_spreads_qty_over_lines_of_the_same_item(self) -> None:
        # Two lines of one item need Selling Settings to allow it.
        with self.change_settings("Selling Settings", allow_multiple_items=1, commit=True):
            self._check_sales_return_two_lines()

    def _check_sales_return_two_lines(self) -> None:
        created = create_sales_invoice(customer=self.customer, items=self._two_line_items(), company=self.company)
        name = created["data"]["name"]
        submit_sales_invoice(name)

        result = create_sales_return(return_against=name, items=[{"item_code": self.item_code, "qty": 3}])
        self.assertTrue(result["success"], result.get("error"))
        ret = frappe.get_doc("Sales Invoice", result["data"]["name"])
        self.assertEqual([row.qty for row in ret.items], [-2, -1])
        self.assertEqual(ret.net_total, -30)

        # 4 of the 7 are left; asking for 5 is refused, not silently capped.
        with self.assertRaises(frappe.ValidationError):
            create_sales_return(return_against=name, items=[{"item_code": self.item_code, "qty": 5}])

    def test_purchase_return_spreads_qty_over_lines_of_the_same_item(self) -> None:
        with self.change_settings("Buying Settings", allow_multiple_items=1, commit=True):
            self._check_purchase_return_two_lines()

    def _check_purchase_return_two_lines(self) -> None:
        created = create_purchase_invoice(supplier=self.supplier, items=self._two_line_items(), company=self.company)
        name = created["data"]["name"]
        submit_purchase_invoice(name)

        result = create_purchase_return(return_against=name, items=[{"item_code": self.item_code, "qty": 3}])
        self.assertTrue(result["success"], result.get("error"))
        ret = frappe.get_doc("Purchase Invoice", result["data"]["name"])
        self.assertEqual([row.qty for row in ret.items], [-2, -1])
        self.assertEqual(ret.net_total, -30)

    # -- Quotation --------------------------------------------------------

    def test_quotation_update_and_delete_on_draft(self) -> None:
        created = create_quotation(customer=self.customer, items=self._items(), company=self.company)
        name = created["data"]["name"]

        updated = update_quotation(name, terms="edited terms")
        self.assertTrue(updated["success"], updated.get("error"))

        deleted = delete_quotation(name)
        self.assertTrue(deleted["success"], deleted.get("error"))
        self.assertFalse(frappe.db.exists("Quotation", name))

    # -- Journal Entry (constructed directly so it stays Draft — create_journal_entry
    #    auto-submits on success, which is the correct behavior for that endpoint but
    #    would leave nothing to exercise the draft-only update/delete guard against) --

    def test_journal_entry_update_and_delete_on_draft(self) -> None:
        cash = frappe.db.get_value("Account", {"company": self.company, "account_type": "Cash"}, "name")
        income = frappe.db.get_value(
            "Account", {"company": self.company, "root_type": "Income", "is_group": 0}, "name"
        )
        self.assertTrue(cash and income, "Test company is missing Cash/Income accounts")

        _, rows = _build_journal_entry_rows(
            [
                {"account": cash, "debit": 20, "credit": 0},
                {"account": income, "debit": 0, "credit": 20},
            ],
            "Bank Entry",
        )
        doc = frappe.get_doc(
            {
                "doctype": "Journal Entry",
                "voucher_type": "Bank Entry",
                "company": self.company,
                "posting_date": frappe.utils.today(),
                "cheque_no": f"CRUD-TEST-{random_string(6)}",
                "cheque_date": frappe.utils.today(),
                "accounts": rows,
            }
        )
        doc.insert(ignore_permissions=True)
        self.assertEqual(int(doc.docstatus or 0), 0)

        updated = update_journal_entry(doc.name, user_remark="edited journal")
        self.assertTrue(updated["success"], updated.get("error"))

        deleted = delete_journal_entry(doc.name)
        self.assertTrue(deleted["success"], deleted.get("error"))
        self.assertFalse(frappe.db.exists("Journal Entry", doc.name))

    # -- Master data: delete succeeds when unreferenced, throws when linked --

    def test_delete_customer_and_supplier_when_unreferenced(self) -> None:
        customer = f"CRUD Delete Customer {random_string(6)}"
        create_customer(customer_name=customer, customer_type="Individual")
        deleted = delete_customer(customer)
        self.assertTrue(deleted["success"], deleted.get("error"))
        self.assertFalse(frappe.db.exists("Customer", customer))

        supplier = f"CRUD Delete Supplier {random_string(6)}"
        create_supplier(supplier_name=supplier, supplier_type="Individual")
        deleted = delete_supplier(supplier)
        self.assertTrue(deleted["success"], deleted.get("error"))
        self.assertFalse(frappe.db.exists("Supplier", supplier))

    def test_delete_customer_blocked_when_linked_to_a_submitted_invoice(self) -> None:
        created = create_sales_invoice(customer=self.customer, items=self._items(), company=self.company)
        submit_sales_invoice(created["data"]["name"])
        with self.assertRaises(frappe.LinkExistsError):
            delete_customer(self.customer)

    def test_delete_account_when_unreferenced(self) -> None:
        parent = frappe.db.get_value(
            "Account", {"company": self.company, "root_type": "Asset", "is_group": 1}, "name"
        )
        self.assertTrue(parent, "Test company is missing a group Asset account")
        leaf = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": f"CRUD Delete Account {random_string(6)}",
                "parent_account": parent,
                "company": self.company,
            }
        )
        leaf.insert(ignore_permissions=True)
        deleted = delete_account(leaf.name)
        self.assertTrue(deleted["success"], deleted.get("error"))
        self.assertFalse(frappe.db.exists("Account", leaf.name))
