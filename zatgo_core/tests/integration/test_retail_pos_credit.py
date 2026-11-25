"""Retail POS credit (pay later) sales: switch, named customer, unpaid / part-paid invoice, GL, stock, collect payment,
credit limit, idempotency, returns and the cash session."""

from __future__ import annotations

from contextlib import contextmanager

import frappe
from frappe.utils import flt, random_string

from zatgo_core.services import pos_session_service as sess
from zatgo_core.services import resto_pos_admin_service as admin
from zatgo_core.services import retail_pos_service as svc
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)
from zatgo_core.tests.integration.test_industries import IndustryTestBase, _set_industries
from zatgo_core.tests.integration.test_resto_pos_order_to_payment import (
    TestRestoPosOrderToPayment as _Base,
)

SETTINGS = "ZatGo POS Settings"


@contextmanager
def credit_switch(on: bool = True):
    """The site switch, put back (committed) afterwards: the sale code commits, so a rollback would not undo it."""
    frappe.db.set_single_value(SETTINGS, "allow_credit_sales", 1 if on else 0)
    frappe.db.commit()
    frappe.clear_document_cache(SETTINGS, SETTINGS)
    try:
        yield
    finally:
        frappe.db.set_single_value(SETTINGS, "allow_credit_sales", 0)
        frappe.db.commit()
        frappe.clear_document_cache(SETTINGS, SETTINGS)


class TestRetailPosCredit(IndustryTestBase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        _Base.company = cls.company
        cls.warehouse = _Base._make_warehouse("RetailCreditTest")
        cash_account = frappe.db.get_value(
            "Account", {"account_type": "Cash", "company": cls.company, "is_group": 0}, "name"
        )
        get_or_create_cash_mode_of_payment(cls.company, cash_account)
        if frappe.db.exists("Company Settings", cls.company):
            frappe.db.set_value("Company Settings", cls.company, "default_warehouse", cls.warehouse)
        else:
            frappe.get_doc(
                {"doctype": "Company Settings", "company": cls.company, "default_warehouse": cls.warehouse}
            ).insert(ignore_permissions=True)
        frappe.db.commit()

    def setUp(self) -> None:
        super().setUp()
        _set_industries("supermarket")
        frappe.set_user("Administrator")
        if sess._open_entry("Administrator", self.company):
            sess.close_session(0, company=self.company)

    # -- helpers ------------------------------------------------------------

    def _item(self, qty: float = 50, price: float = 10) -> str:
        code = f"CRED-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=price, barcode=f"BC{code}")
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        admin.adjust_stock(code, qty, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)
        return code

    def _customer(self, limit: float = 0) -> str:
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": f"Credit Cust {random_string(6)}",
                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
            }
        )
        if limit:
            doc.append("credit_limits", {"company": self.company, "credit_limit": limit})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name

    def _bin(self, code: str) -> float:
        return flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": self.warehouse}, "actual_qty"))

    def _sale(self, code: str, method: str = "credit", cid: str | None = None, qty: float = 2, **kw):
        return svc.create_sale(
            [{"item_code": code, "qty": qty, "rate": 10}],
            method,
            cid or f"cr-{random_string(8)}",
            company=self.company,
            **kw,
        )

    def _receivable_debit(self, invoice: str) -> float:
        return flt(
            frappe.db.sql(
                "select sum(debit) from `tabGL Entry` where voucher_type='Sales Invoice' and voucher_no=%s "
                "and party_type='Customer' and is_cancelled=0",
                invoice,
            )[0][0]
        )

    # -- rules --------------------------------------------------------------

    def test_switch_off_refuses_credit(self) -> None:
        with credit_switch(False):
            with self.assertRaises(frappe.PermissionError):
                self._sale(self._item(), customer_id=self._customer())

    def test_credit_needs_a_named_existing_customer(self) -> None:
        with credit_switch():
            code = self._item()
            for kw in ({}, {"customer_id": "No Such Customer"}, {"customer_name": "Typed At The Till"}, {"customer_id": "Walk-in Customer"}):
                with self.assertRaises(frappe.ValidationError):
                    self._sale(code, **kw)

    def test_credit_is_never_offline(self) -> None:
        with credit_switch():
            with self.assertRaises(frappe.ValidationError):
                self._sale(
                    self._item(),
                    customer_id=self._customer(),
                    offline=1,
                    sale_datetime=frappe.utils.now(),
                    offline_ref="OFF-1",
                    device_id="dev",
                )

    # -- posting ------------------------------------------------------------

    def test_credit_sale_is_posted_unpaid_with_gl_and_stock(self) -> None:
        with credit_switch():
            code, cust = self._item(), self._customer()
            before = self._bin(code)
            cid = f"cr-{random_string(8)}"
            out = self._sale(code, cid=cid, customer_id=cust)
            inv = out["data"]["invoice"]
            si = frappe.get_doc("Sales Invoice", inv["id"])
            self.assertEqual(si.docstatus, 1)
            self.assertEqual(si.customer, cust)
            self.assertAlmostEqual(flt(si.outstanding_amount), flt(si.grand_total), 2)
            self.assertAlmostEqual(flt(inv["outstanding"]), flt(si.grand_total), 2)
            self.assertEqual(out["data"]["payment"]["method"], "credit")
            self.assertEqual(out["data"]["payment"]["amount"], 0)
            self.assertTrue(out["meta"].get("credit"))
            self.assertEqual(frappe.db.count("Payment Entry Reference", {"reference_name": si.name}), 0)
            self.assertAlmostEqual(self._receivable_debit(si.name), flt(si.grand_total), 2)  # receivable up by the total
            self.assertEqual(self._bin(code), before - 2)  # stock left the shelf

            again = self._sale(code, cid=cid, customer_id=cust)  # retry: the same invoice, nothing doubled
            self.assertEqual(again["data"]["invoice"]["id"], si.name)
            self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid}), 1)
            self.assertEqual(self._bin(code), before - 2)

    def test_part_payment_then_collect_the_rest(self) -> None:
        with credit_switch():
            code, cust = self._item(), self._customer()
            out = self._sale(code, customer_id=cust, paid_now=5, paid_method="cash")
            si_name = out["data"]["invoice"]["id"]
            total = flt(out["data"]["invoice"]["total"])
            self.assertAlmostEqual(flt(out["data"]["payment"]["amount"]), 5, 2)
            self.assertAlmostEqual(flt(out["data"]["invoice"]["outstanding"]), total - 5, 2)

            cid = f"col-{random_string(8)}"
            first = svc.collect_payment(si_name, "card", cid)  # no amount = everything still owing
            self.assertAlmostEqual(flt(first["data"]["invoice"]["outstanding"]), 0, 2)
            self.assertAlmostEqual(flt(first["data"]["payment"]["amount"]), total - 5, 2)
            again = svc.collect_payment(si_name, "card", cid)  # the same request twice: one payment
            self.assertEqual(again["data"]["payment"]["id"], first["data"]["payment"]["id"])
            self.assertEqual(frappe.db.count("Payment Entry", {"zatgo_client_id": cid}), 1)
            with self.assertRaises(frappe.ValidationError):  # paid up: a new request is refused
                svc.collect_payment(si_name, "cash", f"col-{random_string(8)}")
            self.assertAlmostEqual(flt(frappe.db.get_value("Sales Invoice", si_name, "outstanding_amount")), 0, 2)

    def test_collect_validates_amount_and_invoice(self) -> None:
        with credit_switch():
            out = self._sale(self._item(), customer_id=self._customer())
            si_name = out["data"]["invoice"]["id"]
            for amount in (0, -3, 10_000):
                with self.assertRaises(frappe.ValidationError):
                    svc.collect_payment(si_name, "cash", f"col-{random_string(8)}", amount=amount)
            with self.assertRaises(frappe.ValidationError):
                svc.collect_payment(si_name, "cheque", f"col-{random_string(8)}")
            partial = svc.collect_payment(si_name, "cash", f"col-{random_string(8)}", amount=4)
            self.assertAlmostEqual(
                flt(partial["data"]["invoice"]["outstanding"]), flt(out["data"]["invoice"]["total"]) - 4, 2
            )

    def test_paid_now_covering_the_total_is_refused(self) -> None:
        with credit_switch():
            code, cust = self._item(), self._customer()
            cid = f"cr-{random_string(8)}"
            with self.assertRaises(frappe.ValidationError):
                self._sale(code, cid=cid, customer_id=cust, paid_now=1000)
            self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid}), 0)  # no orphan draft

    # -- credit limit -------------------------------------------------------

    def test_credit_limit_blocks_and_records_nothing(self) -> None:
        with credit_switch():
            code, cust = self._item(), self._customer(limit=1)
            before = self._bin(code)
            cid = f"cr-{random_string(8)}"
            with self.assertRaises(frappe.ValidationError):
                self._sale(code, cid=cid, customer_id=cust)
            self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid, "docstatus": 1}), 0)
            self.assertEqual(self._bin(code), before)

    def test_balance_and_unpaid_list(self) -> None:
        with credit_switch():
            code, cust = self._item(), self._customer(limit=1000)
            out = self._sale(code, customer_id=cust)
            total = flt(out["data"]["invoice"]["total"])
            bal = svc.customer_balance(cust, self.company)["data"]
            self.assertAlmostEqual(flt(bal["outstanding"]), total, 2)
            self.assertEqual(flt(bal["creditLimit"]), 1000)
            self.assertAlmostEqual(flt(bal["available"]), 1000 - total, 2)
            unpaid = svc.unpaid_invoices(cust, company=self.company)["data"]
            self.assertEqual([r["id"] for r in unpaid], [out["data"]["invoice"]["id"]])
            svc.collect_payment(out["data"]["invoice"]["id"], "cash", f"col-{random_string(8)}")
            self.assertEqual(svc.unpaid_invoices(cust, company=self.company)["data"], [])

    # -- returns and the cash session ---------------------------------------

    def test_return_of_an_unpaid_credit_invoice(self) -> None:
        from erpnext.controllers.sales_and_purchase_return import make_return_doc

        with credit_switch():
            code, cust = self._item(), self._customer()
            out = self._sale(code, customer_id=cust)
            si_name = out["data"]["invoice"]["id"]
            ret = make_return_doc("Sales Invoice", si_name)
            ret.insert(ignore_permissions=True)
            ret.submit()
            frappe.db.commit()
            # ERPNext keeps the credit note's own negative outstanding: the till nets it, so nothing is left to collect.
            self.assertEqual(svc.unpaid_invoices(cust, company=self.company)["data"], [])
            with self.assertRaises(frappe.ValidationError):
                svc.collect_payment(si_name, "cash", f"col-{random_string(8)}")

    def test_unpaid_credit_does_not_count_as_drawer_cash(self) -> None:
        with credit_switch():
            opened = sess.open_session(100, self.company)["data"]
            code, cust = self._item(), self._customer()
            cash_sale = self._sale(code, "cash")
            self._sale(code, customer_id=cust)  # unpaid: no money came in
            paid = flt(cash_sale["data"]["payment"]["amount"])
            running = sess.current(self.company)["data"]
            cash_row = next(m for m in running["methods"] if m["modeOfPayment"] == "Cash")
            self.assertEqual(flt(cash_row["expected"]), 100 + paid)
            view = sess.close_session(100 + paid, opened["id"], company=self.company)["data"]
            cash = next(m for m in view["methods"] if m["modeOfPayment"] == "Cash")
            self.assertEqual(flt(cash["difference"]), 0)
