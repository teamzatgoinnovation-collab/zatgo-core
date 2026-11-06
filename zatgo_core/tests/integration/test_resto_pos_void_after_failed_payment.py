"""A Resto POS payment that fails after the invoice posted: the order keeps the invoice, cannot be voided around it, and
a retry (even under a new client_id) pays that invoice instead of posting a second one. Plus POST-only money endpoints."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import flt, random_string

from zatgo_core.api.v1.resto_pos import billing, orders
from zatgo_core.services import resto_pos_service as svc
from zatgo_core.tests.integration._fixtures import get_or_create_cash_mode_of_payment, get_or_create_test_company


def _failing_payment_entry(*args, **kwargs):
    pe = get_payment_entry(*args, **kwargs)

    def submit():
        raise frappe.ValidationError("simulated payment failure")

    pe.submit = submit
    return pe


class TestRestoPosFailedPayment(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        abbr = frappe.db.get_value("Company", cls.company, "abbr")
        cls.warehouse = f"RestoVoidTest - {abbr}"
        if not frappe.db.exists("Warehouse", cls.warehouse):
            frappe.get_doc({"doctype": "Warehouse", "warehouse_name": "RestoVoidTest", "company": cls.company}).insert(
                ignore_permissions=True
            )
        cash_account = frappe.db.get_value("Account", {"account_type": "Cash", "company": cls.company, "is_group": 0}, "name")
        get_or_create_cash_mode_of_payment(cls.company, cash_account)
        if frappe.db.exists("ZG Company Settings", cls.company):
            frappe.db.set_value("ZG Company Settings", cls.company, "default_warehouse", cls.warehouse)
        else:
            frappe.get_doc({"doctype": "ZG Company Settings", "company": cls.company, "default_warehouse": cls.warehouse}).insert(
                ignore_permissions=True
            )
        frappe.db.commit()

    def setUp(self) -> None:
        self.item = f"RESTOVOID-{random_string(6).upper()}"
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": self.item,
                "item_name": self.item,
                "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
                "stock_uom": "Nos",
                "is_stock_item": 1,
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": self.company,
                "items": [{"item_code": self.item, "qty": 10, "t_warehouse": self.warehouse, "basic_rate": 10}],
            }
        ).insert(ignore_permissions=True).submit()
        created = svc.create_order(
            company=self.company,
            channel="counter",
            items=[{"item_code": self.item, "qty": 1, "rate": 10}],
            client_id=f"test-voidpay-{random_string(8)}",
        )
        self.order_id = created["data"]["id"]
        frappe.db.commit()

    def _fail_payment(self, client_id: str) -> str:
        with patch(
            "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry", side_effect=_failing_payment_entry
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                svc.pay(self.order_id, "cash", client_id)
        self.assertIn("Retry the payment", str(ctx.exception))
        invoice = frappe.db.get_value("ZG Order", self.order_id, "sales_invoice")
        self.assertTrue(invoice, "the order must remember the invoice that posted")
        self.assertEqual(frappe.db.get_value("Sales Invoice", invoice, "docstatus"), 1)
        return invoice

    def _bin_qty(self) -> float:
        return flt(frappe.db.get_value("Bin", {"item_code": self.item, "warehouse": self.warehouse}, "actual_qty"))

    def test_order_with_a_posted_invoice_cannot_be_voided(self) -> None:
        invoice = self._fail_payment(f"test-voidpay-{random_string(8)}")
        with self.assertRaises(frappe.ValidationError) as ctx:
            svc.void_order(self.order_id)
        self.assertIn(invoice, str(ctx.exception))
        self.assertNotEqual(frappe.db.get_value("ZG Order", self.order_id, "status"), "Void")

    def test_retry_under_a_new_client_id_pays_the_same_invoice(self) -> None:
        invoice = self._fail_payment(f"test-voidpay-{random_string(8)}")
        self.assertEqual(self._bin_qty(), 9)

        paid = svc.pay(self.order_id, "cash", f"test-voidpay-{random_string(8)}")

        self.assertEqual(paid["data"]["order"]["status"], "paid")
        self.assertEqual(frappe.db.get_value("ZG Order", self.order_id, "sales_invoice"), invoice)
        self.assertEqual(frappe.db.count("Sales Invoice Item", {"item_code": self.item, "docstatus": 1}), 1)
        self.assertEqual(self._bin_qty(), 9, "stock must go out once")
        self.assertEqual(flt(frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount")), 0)

    def test_order_can_be_voided_once_its_invoice_is_cancelled(self) -> None:
        invoice = self._fail_payment(f"test-voidpay-{random_string(8)}")
        frappe.get_doc("Sales Invoice", invoice).cancel()
        frappe.db.commit()

        voided = svc.void_order(self.order_id)

        self.assertEqual(voided["data"]["status"], "void")
        self.assertEqual(self._bin_qty(), 10, "cancelling the invoice returned the stock")


class TestRestoPosWritesArePostOnly(IntegrationTestCase):
    def test_writes_refuse_get(self) -> None:
        for fn in (
            billing.pay,
            billing.mark_billing,
            orders.create,
            orders.add_item,
            orders.update_item_qty,
            orders.send,
            orders.set_note,
            orders.void,
            orders.give_to_delivery,
        ):
            self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[fn], ["POST"], fn.__name__)
