"""Retail (Supermarket) POS: profile pos_mode, one-shot sale (Sales Invoice + Payment
Entry, stock out, tax, discount, idempotency) and the catalog / stock / customers /
payments / dashboard endpoints working with Restaurant OFF and Supermarket ON."""

from __future__ import annotations

import frappe
from frappe.utils import flt, random_string, today

from zatgo_core.api.v1.retail_pos import catalog as r_catalog
from zatgo_core.api.v1.retail_pos import customers as r_customers
from zatgo_core.api.v1.retail_pos import dashboard as r_dashboard
from zatgo_core.api.v1.retail_pos import payments as r_payments
from zatgo_core.api.v1.retail_pos import sale as r_sale
from zatgo_core.api.v1.retail_pos import stock as r_stock
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


class TestRetailPos(IndustryTestBase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        _Base.company = cls.company
        cls.warehouse = _Base._make_warehouse("RetailPosTest")
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
        super().setUp()  # every industry off
        _set_industries("supermarket")
        frappe.set_user("Administrator")

    def _item(self, qty: float = 10, price: float = 10) -> str:
        code = f"RETAIL-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=price, barcode=f"BC{code}")
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        admin.adjust_stock(code, qty, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)
        return code

    def _bin(self, code: str) -> float:
        return flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": self.warehouse}, "actual_qty"))

    def _sale(self, code: str, qty: float = 2, cid: str | None = None, **kw):
        return svc.create_sale(
            [{"item_code": code, "qty": qty, "rate": 10}],
            kw.pop("method", "cash"),
            cid or f"rs-{random_string(8)}",
            company=self.company,
            **kw,
        )

    # -- profile / gate -----------------------------------------------------

    def test_profile_pos_mode(self) -> None:
        data = admin.get_profile()["data"]
        self.assertEqual(data["pos_mode"], "retail")
        self.assertTrue(data["retail"])
        self.assertFalse(data["restaurant"])
        self.assertIn("industries", data)
        _set_industries("supermarket", "restaurant")
        data = admin.get_profile()["data"]
        self.assertEqual(data["pos_mode"], "restaurant")  # Restaurant wins
        self.assertTrue(data["retail"])
        _set_industries("restaurant")
        data = admin.get_profile()["data"]
        self.assertEqual((data["pos_mode"], data["retail"]), ("restaurant", False))
        _set_industries()
        data = admin.get_profile()["data"]
        self.assertIsNone(data["pos_mode"])

    def test_profile_carries_the_sellers_invoice_details(self) -> None:
        company = admin.get_profile()["data"]["company"]  # the company the POS sells for (the site's default)
        fields = ["tax_id", "registration_details", "phone_no"]
        before = frappe.db.get_value("Company", company, fields, as_dict=True)
        self.addCleanup(frappe.db.set_value, "Company", company, dict(before))
        frappe.db.set_value("Company", company, {"tax_id": "300000000000003", "registration_details": "CR 1010000000", "phone_no": "0112345678"})
        info = admin.get_profile()["data"]["company_info"]
        self.assertEqual(info["vat_number"], "300000000000003")
        self.assertEqual(info["cr_number"], "CR 1010000000")
        self.assertEqual(info["phone"], "0112345678")
        self.assertTrue(info["name"])
        for key in ("name_ar", "email", "website", "address"):
            self.assertIn(key, info)

    def test_customers_carry_vat_cr_and_address(self) -> None:
        name = f"Invoice Customer {random_string(5)}"
        res = admin.upsert_customer(customer_name=name, client_id=f"cu-{random_string(8)}")
        cid = res["data"]["id"]
        frappe.db.set_value("Customer", cid, "tax_id", "310000000000003")
        if frappe.db.has_column("Customer", "zatgo_cr_number"):
            frappe.db.set_value("Customer", cid, "zatgo_cr_number", "CR 2050000000")
        rows = admin.list_customers(search=name)["data"]
        row = next(r for r in rows if r["id"] == cid)
        self.assertEqual(row["vat_number"], "310000000000003")
        self.assertIn("cr_number", row)
        self.assertIn("address", row)

    def test_sale_response_carries_the_stored_qr_fields(self) -> None:
        code = self._item()
        res = self._sale(code)
        inv = res["data"]["invoice"]
        self.assertIn("zatcaQr", inv)
        self.assertIn("zatcaQrP2", inv)

    def test_api_gate(self) -> None:
        self.assertFalse(self._gate_404("zatgo_core.api.v1.retail_pos.sale.create"))
        self.assertTrue(self._gate_404("zatgo_core.api.v1.resto_pos.tables.list"))  # Restaurant OFF
        _set_industries()
        self.assertTrue(self._gate_404("zatgo_core.api.v1.retail_pos.sale.create"))
        _set_industries("restaurant")
        self.assertTrue(self._gate_404("zatgo_core.api.v1.retail_pos.sale.create"))
        self.assertFalse(self._gate_404("zatgo_core.api.v1.resto_pos.tables.list"))

    # -- sale ---------------------------------------------------------------

    def test_sale_happy_path(self) -> None:
        code = self._item(qty=10)
        res = self._sale(code, qty=3)
        self.assertTrue(res["success"], res.get("error"))
        inv, pay = res["data"]["invoice"], res["data"]["payment"]
        si = frappe.get_doc("Sales Invoice", inv["id"])
        self.assertEqual(si.docstatus, 1)
        self.assertEqual(si.update_stock, 1)
        self.assertEqual(inv["total"], si.grand_total)
        self.assertEqual(inv["subtotal"], flt(si.total))
        self.assertEqual(inv["tax"], flt(si.total_taxes_and_charges))
        self.assertEqual(self._bin(code), 7)  # stock out
        self.assertEqual(
            frappe.db.count("Stock Ledger Entry", {"voucher_no": si.name, "item_code": code, "is_cancelled": 0}), 1
        )
        gl = frappe.get_all("GL Entry", filters={"voucher_no": si.name, "is_cancelled": 0}, fields=["debit", "credit"])
        self.assertTrue(gl)
        self.assertAlmostEqual(sum(flt(g.debit) for g in gl), sum(flt(g.credit) for g in gl), 2)
        pe = frappe.get_doc("Payment Entry", pay["id"])
        self.assertEqual(pe.docstatus, 1)
        self.assertEqual(pe.mode_of_payment, "Cash")
        self.assertEqual(pay["method"], "cash")
        self.assertEqual(pay["amount"], si.grand_total)
        self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 0)
        self.assertEqual(si.zatgo_client_id + ":pay", pe.zatgo_client_id)

    def test_sale_of_an_item_with_no_cost_yet(self) -> None:
        """Stock received with no cost has no valuation: the sale posts (COGS 0) instead of ERPNext's zero-rate error."""
        code = f"RETAIL-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=0, barcode=f"BC{code}")
        admin.adjust_stock(code, 5, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)  # received at no cost
        frappe.db.set_value("Item", code, "standard_rate", 10)
        res = self._sale(code, qty=1)
        self.assertTrue(res["success"], res.get("error"))
        si = frappe.get_doc("Sales Invoice", res["data"]["invoice"]["id"])
        self.assertEqual(si.docstatus, 1)
        self.assertEqual(si.items[0].allow_zero_valuation_rate, 1)
        # an item that does have a cost keeps ERPNext's guard
        costed = self._item(qty=5)
        si2 = frappe.get_doc("Sales Invoice", self._sale(costed, qty=1)["data"]["invoice"]["id"])
        self.assertEqual(si2.items[0].allow_zero_valuation_rate, 0)

    def test_sale_uses_the_warehouse_chosen_in_pos_settings(self) -> None:
        other = _Base._make_warehouse("RetailPosSettingsWh")
        pos = "ZG POS Settings"
        stored = frappe.db.sql("select value from tabSingles where doctype = %s and field = 'default_warehouse'", (pos,))
        try:
            frappe.db.set_single_value(pos, "default_warehouse", other)
            code = f"RETAIL-{random_string(6).upper()}"
            admin.upsert_item(item_code=code, item_name=code, price=10, barcode=f"BC{code}")
            frappe.db.set_value("Item", code, "valuation_rate", 5)
            admin.adjust_stock(code, 5, f"adj-{random_string(8)}", warehouse=other, company=self.company)
            res = self._sale(code, 2)
            self.assertEqual(frappe.db.get_value("Sales Invoice Item", {"parent": res["data"]["invoice"]["id"]}, "warehouse"), other)
        finally:
            if stored:
                frappe.db.set_single_value(pos, "default_warehouse", stored[0][0])
            else:
                frappe.db.sql("delete from tabSingles where doctype = %s and field = 'default_warehouse'", (pos,))
            frappe.db.commit()

    def test_sale_discount(self) -> None:
        code = self._item(qty=10)
        res = self._sale(code, qty=2, discount_type="percent", discount_value=10)
        si = frappe.get_doc("Sales Invoice", res["data"]["invoice"]["id"])
        self.assertEqual(si.net_total, 18)
        self.assertEqual(res["data"]["invoice"]["discount"], 2)
        self.assertEqual(res["data"]["payment"]["amount"], si.grand_total)
        with self.assertRaises(frappe.ValidationError):
            self._sale(code, qty=1, discount_type="fixed", discount_value=999)

    def test_sale_idempotent_double_submit(self) -> None:
        code = self._item(qty=10)
        cid = f"rs-{random_string(8)}"
        first = self._sale(code, qty=2, cid=cid)
        second = self._sale(code, qty=2, cid=cid)
        self.assertTrue(second["meta"]["idempotent"])
        self.assertEqual(first["data"]["invoice"]["id"], second["data"]["invoice"]["id"])
        self.assertEqual(first["data"]["payment"]["id"], second["data"]["payment"]["id"])
        self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid}), 1)
        self.assertEqual(frappe.db.count("Payment Entry", {"zatgo_client_id": f"{cid}:pay"}), 1)
        self.assertEqual(self._bin(code), 8)  # stock moved once

    def test_sale_validation(self) -> None:
        code = self._item(qty=10)
        with self.assertRaises(frappe.ValidationError):
            self._sale(code, method="bitcoin")
        with self.assertRaises(frappe.ValidationError):
            svc.create_sale([], "cash", f"rs-{random_string(8)}", company=self.company)

    def test_sale_rejects_bad_rates(self) -> None:
        code = self._item(qty=10)
        with self.assertRaises(frappe.ValidationError):
            svc.create_sale([{"item_code": code, "qty": 1, "rate": -5}], "cash", f"rs-{random_string(8)}", company=self.company)
        self.assertEqual(self._bin(code), 10)

    def test_sale_rate_floor_for_cashier(self) -> None:
        code = self._item(qty=10, price=10)
        user = "retail.cashier@example.com"
        if not frappe.db.exists("User", user):
            frappe.get_doc(
                {"doctype": "User", "email": user, "first_name": "Cashier", "send_welcome_email": 0,
                 "roles": [{"role": "Sales User"}]}
            ).insert(ignore_permissions=True)
        frappe.set_user(user)
        try:
            with self.assertRaises(frappe.ValidationError):
                svc._validate_rates([{"item_code": code, "rate": 0}])
            with self.assertRaises(frappe.ValidationError):
                svc._validate_rates([{"item_code": code, "rate": 1}])
            svc._validate_rates([{"item_code": code, "rate": 10}])
        finally:
            frappe.set_user("Administrator")

    def test_sale_full_discount_has_no_payment_entry(self) -> None:
        code = self._item(qty=10)
        res = self._sale(code, qty=1, discount_type="percent", discount_value=100)
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(res["data"]["invoice"]["total"], 0)
        self.assertEqual(res["data"]["payment"]["amount"], 0)
        cid = frappe.db.get_value("Sales Invoice", res["data"]["invoice"]["id"], "zatgo_client_id")
        self.assertEqual(frappe.db.count("Payment Entry", {"zatgo_client_id": f"{cid}:pay"}), 0)
        self.assertEqual(self._bin(code), 9)

    def test_card_sale_posts_to_mode_account(self) -> None:
        code = self._item(qty=10)
        if not frappe.db.exists("Mode of Payment", "Card"):
            frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": "Card", "type": "Bank"}).insert(
                ignore_permissions=True
            )
        bank = frappe.db.get_value("Account", {"account_type": "Bank", "company": self.company, "is_group": 0}, "name")
        if not bank:
            self.skipTest("no Bank account in the test company")
        mop = frappe.get_doc("Mode of Payment", "Card")
        if not any(a.company == self.company for a in mop.accounts):
            mop.append("accounts", {"company": self.company, "default_account": bank})
            mop.save(ignore_permissions=True)
        res = self._sale(code, qty=1, method="card")
        pe = frappe.get_doc("Payment Entry", res["data"]["payment"]["id"])
        self.assertEqual(pe.paid_to, bank)
        self.assertTrue(
            frappe.db.exists("GL Entry", {"voucher_no": pe.name, "account": bank, "is_cancelled": 0, "debit": [">", 0]})
        )

    def test_replay_checks_basket(self) -> None:
        code = self._item(qty=10)
        cid = f"rs-{random_string(8)}"
        self._sale(code, qty=2, cid=cid)
        with self.assertRaises(frappe.ValidationError):
            self._sale(code, qty=3, cid=cid)

    def test_sale_with_customer(self) -> None:
        code = self._item(qty=5)
        res = self._sale(code, qty=1, customer_name=f"Retail Cust {random_string(5)}", customer_phone="0500000001")
        self.assertTrue(res["data"]["invoice"]["customer"].startswith("Retail Cust"))

    # -- back office with Restaurant OFF ------------------------------------

    def test_backoffice_endpoints(self) -> None:
        self.assertNotIn("restaurant", admin.get_profile()["data"]["industries"])
        code = f"RETAIL-{random_string(6).upper()}"
        r_catalog.upsert(item_code=code, item_name=code, price=12, barcode=f"BC{code}")
        self.assertTrue(r_catalog.by_barcode(f"BC{code}")["data"])
        self.assertTrue(r_catalog.get(code)["success"])
        self.assertTrue(r_catalog.list()["success"])
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        admin.adjust_stock(code, 6, f"adj-{random_string(8)}", self.warehouse, company=self.company)
        self.assertTrue(callable(r_stock.adjust))
        rows = r_stock.list(self.warehouse, search=code)["data"]
        self.assertEqual(next(r for r in rows if r["id"] == code)["onHand"], 6)
        name = f"Retail Cust {random_string(5)}"
        cid = r_customers.upsert(customer_name=name)["data"]["id"]
        self.assertTrue(any(c["id"] == cid for c in r_customers.list(search=name)["data"]))
        r_catalog.disable(code)
        self.assertEqual(frappe.db.get_value("Item", code, "disabled"), 1)

    def test_payments_and_dashboard(self) -> None:
        code = self._item(qty=10)
        before = svc.dashboard_counts(self.company)["data"]
        res = self._sale(code, qty=2)
        pay_id = res["data"]["payment"]["id"]
        total = res["data"]["invoice"]["total"]
        payments = svc.list_payments(today(), company=self.company)["data"]
        row = next(p for p in payments if p["id"] == pay_id)
        self.assertEqual(row["orderId"], res["data"]["invoice"]["id"])
        self.assertEqual(row["method"], "cash")
        self.assertEqual(row["amount"], total)
        after = svc.dashboard_counts(self.company)["data"]
        self.assertEqual(after["paymentsToday"], before["paymentsToday"] + 1)
        self.assertAlmostEqual(after["todaySales"] - before["todaySales"], total, 2)
        self.assertEqual(after["revenueToday"], after["todaySales"])
        self.assertEqual(after["itemsSoldToday"] - before["itemsSoldToday"], 2)
        self.assertIn("lowStock", after)
        # whitelisted wrappers answer too (default company path)
        self.assertTrue(r_payments.list(today())["success"])
        self.assertTrue(r_dashboard.counts()["success"])
        self.assertTrue(callable(r_sale.create))
