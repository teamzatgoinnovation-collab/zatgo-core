"""POS cash session on ERPNext's POS Opening / POS Closing Entry: open (idempotent), the expected cash fed from the retail
sales' Payment Entries, close with / without a variance, and the guards (no open session, closed session replay)."""

from __future__ import annotations

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


class TestPosSession(IndustryTestBase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        _Base.company = cls.company
        cls.warehouse = _Base._make_warehouse("PosSessionTest")
        cash_account = frappe.db.get_value(
            "Account", {"account_type": "Cash", "company": cls.company, "is_group": 0}, "name"
        )
        get_or_create_cash_mode_of_payment(cls.company, cash_account)
        if frappe.db.exists("ZG Company Settings", cls.company):
            frappe.db.set_value("ZG Company Settings", cls.company, "default_warehouse", cls.warehouse)
        else:
            frappe.get_doc(
                {"doctype": "ZG Company Settings", "company": cls.company, "default_warehouse": cls.warehouse}
            ).insert(ignore_permissions=True)
        frappe.db.commit()

    def setUp(self) -> None:
        super().setUp()
        _set_industries("supermarket")
        frappe.set_user("Administrator")
        # A session left open by an earlier test is closed first, so every test starts with none.
        if sess._open_entry("Administrator", self.company):
            sess.close_session(0, company=self.company)

    def _item(self) -> str:
        code = f"SESS-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=10, barcode=f"BC{code}")
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        admin.adjust_stock(code, 50, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)
        return code

    def _sale(self, code: str, method: str = "cash") -> dict:
        return svc.create_sale(
            [{"item_code": code, "qty": 2, "rate": 10}], method, f"ss-{random_string(8)}", company=self.company
        )["data"]

    def _cash_row(self, summary: dict) -> dict:
        return next(m for m in summary["methods"] if m["modeOfPayment"] == "Cash")

    def test_open_is_a_native_opening_entry_and_idempotent(self) -> None:
        first = sess.open_session(100, self.company)
        self.assertTrue(first["meta"]["created"])
        entry = frappe.get_doc("POS Opening Entry", first["data"]["id"])
        self.assertEqual((entry.status, entry.user, entry.docstatus), ("Open", "Administrator", 1))
        self.assertEqual(flt(next(r.opening_amount for r in entry.balance_details if r.mode_of_payment == "Cash")), 100)
        again = sess.open_session(999, self.company)  # a repeat (retry) never opens a second one or changes the float
        self.assertTrue(again["meta"]["idempotent"])
        self.assertEqual(again["data"]["id"], first["data"]["id"])
        self.assertEqual(frappe.db.count("POS Opening Entry", {"user": "Administrator", "status": "Open"}), 1)
        self.assertEqual(sess.current(self.company)["data"]["id"], first["data"]["id"])

    def test_negative_float_refused(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            sess.open_session(-1, self.company)

    def test_close_without_open_session_refused(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            sess.close_session(0, company=self.company)

    def test_expected_cash_comes_from_the_sales_and_close_is_native(self) -> None:
        opened = sess.open_session(100, self.company)["data"]
        code = self._item()
        cash_sale = self._sale(code, "cash")
        self._sale(code, "card")
        paid = flt(cash_sale["payment"]["amount"])
        self.assertGreater(paid, 0)

        running = sess.current(self.company)["data"]
        self.assertEqual(running["salesCount"], 2)
        self.assertEqual(flt(self._cash_row(running)["expected"]), 100 + paid)  # card money is not in the drawer

        closed = sess.close_session(100 + paid, opened["id"], company=self.company)
        view = closed["data"]
        cash = next(m for m in view["methods"] if m["modeOfPayment"] == "Cash")
        self.assertEqual((flt(cash["expected"]), flt(cash["counted"]), flt(cash["difference"])), (100 + paid, 100 + paid, 0))
        self.assertEqual(frappe.db.get_value("POS Opening Entry", opened["id"], "status"), "Closed")
        closing = frappe.get_doc("POS Closing Entry", view["closingId"])
        self.assertEqual((closing.docstatus, closing.user), (1, "Administrator"))
        self.assertIsNone(sess.current(self.company)["data"])

    def test_variance_is_recorded(self) -> None:
        opened = sess.open_session(50, self.company)["data"]
        self._sale(self._item(), "cash")
        expected = flt(self._cash_row(sess.current(self.company)["data"])["expected"])
        view = sess.close_session(expected - 5, opened["id"], company=self.company)["data"]
        cash = next(m for m in view["methods"] if m["modeOfPayment"] == "Cash")
        self.assertEqual(flt(cash["difference"]), -5)

    def test_close_retry_returns_the_same_closing_entry(self) -> None:
        opened = sess.open_session(10, self.company)["data"]
        first = sess.close_session(10, opened["id"], company=self.company)
        again = sess.close_session(10, opened["id"], company=self.company)
        self.assertTrue(again["meta"]["idempotent"])
        self.assertEqual(again["data"]["closingId"], first["data"]["closingId"])
        self.assertEqual(frappe.db.count("POS Closing Entry", {"pos_opening_entry": opened["id"]}), 1)

    def test_sales_before_the_session_are_not_counted(self) -> None:
        code = self._item()
        self._sale(code, "cash")
        sess.open_session(0, self.company)
        running = sess.current(self.company)["data"]
        self.assertEqual((running["salesCount"], flt(self._cash_row(running)["expected"])), (0, 0))
