"""Retail POS split payment (one invoice, one Payment Entry per mode of payment), card reference, configured modes,
the whole-number UOM flag and the tax rows the till shows."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.utils import flt, random_string

from zatgo_core.services import erpnext_reads
from zatgo_core.services import resto_pos_admin_service as admin
from zatgo_core.services import retail_pos_service as svc
from zatgo_core.services.offline_sale import PaymentPendingError
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)
from zatgo_core.tests.integration.test_industries import IndustryTestBase, _set_industries
from zatgo_core.tests.integration.test_resto_pos_order_to_payment import (
    TestRestoPosOrderToPayment as _Base,
)

SETTINGS = "ZG POS Settings"


@contextmanager
def pos_setting(field: str, value):
    """A ZG POS Settings value, put back (committed) afterwards: the sale code commits, so a rollback would not undo it."""
    frappe.db.set_single_value(SETTINGS, field, value)
    frappe.db.commit()
    frappe.clear_document_cache(SETTINGS, SETTINGS)
    try:
        yield
    finally:
        frappe.db.set_single_value(SETTINGS, field, 1 if field == "allow_split_payment" else 0)
        frappe.db.commit()
        frappe.clear_document_cache(SETTINGS, SETTINGS)


class TestRetailPosSplit(IndustryTestBase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        _Base.company = cls.company
        cls.warehouse = _Base._make_warehouse("RetailSplitTest")
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

    def _item(self, qty: float = 50, price: float = 10, uom: str | None = None) -> str:
        code = f"SPLIT-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=price, barcode=f"BC{code}", uom=uom)
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        admin.adjust_stock(code, qty, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)
        return code

    def _bin(self, code: str) -> float:
        return flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": self.warehouse}, "actual_qty"))

    def _sale(self, code: str, payments, cid: str | None = None, qty: float = 10, **kw):
        return svc.create_sale(
            [{"item_code": code, "qty": qty, "rate": 10}],
            "cash",
            cid or f"sp-{random_string(8)}",
            company=self.company,
            payments=payments,
            **kw,
        )

    def _pes(self, cid: str) -> list[str]:
        return frappe.get_all(
            "Payment Entry", filters={"zatgo_client_id": ["like", f"{cid}:pay%"], "docstatus": 1}, pluck="name", order_by="creation asc"
        )

    # -- split ----------------------------------------------------------------

    def test_split_posts_one_invoice_and_one_payment_entry_per_mode(self) -> None:
        code = self._item()
        before = self._bin(code)
        cid = f"sp-{random_string(8)}"
        out = self._sale(code, [{"method": "cash", "amount": 40}, {"method": "card", "amount": 60}], cid=cid)
        data = out["data"]
        self.assertAlmostEqual(flt(data["invoice"]["total"]), 100, 2)
        self.assertEqual([p["method"] for p in data["payments"]], ["cash", "card"])
        self.assertEqual([flt(p["amount"]) for p in data["payments"]], [40, 60])
        self.assertAlmostEqual(flt(data["payment"]["amount"]), 100, 2)  # the sale's payment is all of them
        self.assertAlmostEqual(flt(data["invoice"]["outstanding"]), 0, 2)
        names = self._pes(cid)
        self.assertEqual(len(names), 2)
        self.assertEqual(
            sorted((frappe.db.get_value("Payment Entry", n, "mode_of_payment"), flt(frappe.db.get_value("Payment Entry", n, "paid_amount"))) for n in names),
            [("Card", 60.0), ("Cash", 40.0)],
        )
        self.assertEqual(self._bin(code), before - 10)  # stock left once, not per payment
        self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid}), 1)

    def test_split_replay_is_idempotent(self) -> None:
        code = self._item()
        cid = f"sp-{random_string(8)}"
        pay = [{"method": "cash", "amount": 30}, {"method": "card", "amount": 70}]
        first = self._sale(code, pay, cid=cid)
        again = self._sale(code, pay, cid=cid)
        self.assertEqual(again["data"]["invoice"]["id"], first["data"]["invoice"]["id"])
        self.assertEqual([p["id"] for p in again["data"]["payments"]], [p["id"] for p in first["data"]["payments"]])
        self.assertEqual(len(self._pes(cid)), 2)

    def test_second_payment_failing_leaves_the_first_and_replay_completes_it(self) -> None:
        code = self._item()
        cid = f"sp-{random_string(8)}"
        pay = [{"method": "cash", "amount": 25}, {"method": "card", "amount": 75}]
        original, seen = Document.submit, {"pe": 0}

        def flaky(doc, *a, **k):
            if doc.doctype == "Payment Entry":
                seen["pe"] += 1
                if seen["pe"] == 2:
                    raise frappe.ValidationError("terminal offline")
            return original(doc, *a, **k)

        with patch.object(Document, "submit", flaky):
            with self.assertRaises(PaymentPendingError):
                self._sale(code, pay, cid=cid)
        si = frappe.db.get_value("Sales Invoice", {"zatgo_client_id": cid}, ["name", "outstanding_amount"], as_dict=True)
        self.assertAlmostEqual(flt(si.outstanding_amount), 75, 2)  # the cash is in, the card is still owing
        self.assertEqual(len(self._pes(cid)), 1)
        done = self._sale(code, pay, cid=cid)  # the retry only posts what is missing
        self.assertEqual(done["data"]["invoice"]["id"], si.name)
        self.assertEqual(len(self._pes(cid)), 2)
        self.assertAlmostEqual(flt(done["data"]["invoice"]["outstanding"]), 0, 2)

    def test_payments_must_add_up_to_the_total(self) -> None:
        code = self._item()
        for pay in (
            [{"method": "cash", "amount": 40}, {"method": "card", "amount": 50}],  # short
            [{"method": "cash", "amount": 60}, {"method": "card", "amount": 50}],  # over
        ):
            cid = f"sp-{random_string(8)}"
            with self.assertRaises(frappe.ValidationError):
                self._sale(code, pay, cid=cid)
            self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid}), 0)  # no orphan draft
            self.assertEqual(self._pes(cid), [])

    def test_a_cent_of_rounding_goes_on_the_last_payment(self) -> None:
        code = self._item()
        cid = f"sp-{random_string(8)}"
        out = self._sale(code, [{"method": "cash", "amount": 40}, {"method": "card", "amount": 59.98}], cid=cid)  # total 100
        self.assertAlmostEqual(flt(out["data"]["invoice"]["outstanding"]), 0, 2)
        self.assertEqual([flt(p["amount"]) for p in out["data"]["payments"]], [40, 60])
        one = self._sale(code, [{"method": "cash", "amount": 100.02}])  # a single row too
        self.assertAlmostEqual(flt(one["data"]["invoice"]["outstanding"]), 0, 2)

    def test_bad_rows_are_refused(self) -> None:
        code = self._item()
        for pay in (
            [{"method": "cheque", "amount": 100}],
            [{"method": "cash", "amount": 0}, {"method": "card", "amount": 100}],
            [{"method": "cash", "amount": -5}, {"method": "card", "amount": 105}],
            "not json",
            {"method": "cash"},
        ):
            with self.assertRaises(frappe.ValidationError):
                self._sale(code, pay)

    def test_split_needs_the_setting(self) -> None:
        code = self._item()
        with pos_setting("allow_split_payment", 0):
            with self.assertRaises(frappe.PermissionError):
                self._sale(code, [{"method": "cash", "amount": 40}, {"method": "card", "amount": 60}])
            ok = self._sale(code, [{"method": "cash", "amount": 100}])  # one payment is not a split
            self.assertEqual(len(ok["data"]["payments"]), 1)

    def test_split_is_never_offline(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            self._sale(
                self._item(),
                [{"method": "cash", "amount": 40}, {"method": "card", "amount": 60}],
                offline=1,
                sale_datetime=frappe.utils.now(),
                offline_ref="OFF-S1",
                device_id="dev",
            )

    def test_a_mode_that_is_not_enabled_is_refused(self) -> None:
        code = self._item()
        had = frappe.db.get_value("Mode of Payment", "Wallet", "enabled")
        if had is None:
            self.skipTest("this site has no Wallet Mode of Payment")
        frappe.db.set_value("Mode of Payment", "Wallet", "enabled", 0)
        frappe.db.commit()
        try:
            with self.assertRaises(frappe.ValidationError):
                self._sale(code, [{"method": "wallet", "amount": 100}])
        finally:
            frappe.db.set_value("Mode of Payment", "Wallet", "enabled", had)
            frappe.db.commit()

    # -- reference and single payment -----------------------------------------

    def test_card_reference_is_kept_on_the_payment_entry(self) -> None:
        code = self._item()
        cid = f"sp-{random_string(8)}"
        self._sale(code, [{"method": "card", "amount": 100, "reference": "TXN-4471"}], cid=cid)
        (pe,) = self._pes(cid)
        self.assertEqual(frappe.db.get_value("Payment Entry", pe, "reference_no"), "TXN-4471")

    def test_payments_list_beats_method_and_old_calls_still_work(self) -> None:
        code = self._item()
        via_list = svc.create_sale(
            [{"item_code": code, "qty": 10, "rate": 10}], "whatever", f"sp-{random_string(8)}",
            company=self.company, payments=[{"method": "cash", "amount": 100}],
        )
        self.assertEqual(via_list["data"]["payment"]["method"], "cash")
        old = svc.create_sale([{"item_code": code, "qty": 10, "rate": 10}], "cash", f"sp-{random_string(8)}", company=self.company)
        self.assertAlmostEqual(flt(old["data"]["payment"]["amount"]), 100, 2)
        self.assertAlmostEqual(flt(old["data"]["invoice"]["outstanding"]), 0, 2)

    # -- profile and catalog extras -------------------------------------------

    def test_profile_carries_tax_rows(self) -> None:
        data = admin.get_profile()["data"]
        self.assertIsInstance(data["tax_rows"], list)
        for row in data["tax_rows"]:
            self.assertIn("description", row)
            self.assertIn("rate", row)
        self.assertIn("payment_modes", data)

    def test_catalog_rows_say_whether_the_uom_is_whole_number(self) -> None:
        uom = frappe.db.get_value("Item", self._item(), "stock_uom")
        row = {"stock_uom": uom}
        erpnext_reads._fill_whole_uom([row])
        expected = int(frappe.db.get_value("UOM", uom, "must_be_whole_number") or 0)
        self.assertEqual(row["must_be_whole_number"], expected)
        self.assertEqual(erpnext_reads.map_item_row({"name": "X", "stock_uom": uom, **row})["must_be_whole_number"], expected)
        # unknown stays absent: the till then allows decimals, as before
        self.assertNotIn("must_be_whole_number", erpnext_reads.map_item_row({"name": "X", "stock_uom": uom}))

    def test_customer_can_be_created_and_updated_with_a_vat_number(self) -> None:
        made = admin.upsert_customer(customer_name=f"Vat Cust {random_string(6)}", vat_number="310123456700003")
        self.assertEqual(made["data"]["vat_number"], "310123456700003")
        cid = made["data"]["id"]
        self.assertEqual(frappe.db.get_value("Customer", cid, "tax_id"), "310123456700003")
        changed = admin.upsert_customer(customer_id=cid, vat_number="300000000000003")
        self.assertEqual(changed["data"]["vat_number"], "300000000000003")
        kept = admin.upsert_customer(customer_id=cid, phone="0500000000")  # no vat_number sent: left alone
        self.assertEqual(kept["data"]["vat_number"], "300000000000003")
