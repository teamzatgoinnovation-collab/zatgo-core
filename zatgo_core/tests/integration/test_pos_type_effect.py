"""POS Type (ZG POS Settings) really changes what the ZatGo POS does: the profile and settings the POS reads, which
engine answers (restaurant or retail), and a real sale through that engine -- Sales Invoice, Payment Entry and stock.

Restaurant and Cafe run the restaurant engine, Supermarket and General Retail the retail one; Pharmacy and Electrical
are listed but refused. Saving a type switches its industry on and never switches the other one off."""

from __future__ import annotations

import frappe
from frappe.utils import flt, random_string

from zatgo_core.api.v1 import pos_settings as pos_settings_api
from zatgo_core.industries import gate
from zatgo_core.services import app_gate, pos_settings
from zatgo_core.services import resto_pos_admin_service as admin
from zatgo_core.services import resto_pos_service as resto
from zatgo_core.services import retail_pos_service as retail
from zatgo_core.services.ui_apps import SETTINGS as SYSTEM
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)
from zatgo_core.tests.integration.test_industries import IndustryTestBase, _set_industries
from zatgo_core.tests.integration.test_resto_pos_order_to_payment import (
    TestRestoPosOrderToPayment as _Base,
)

# POS Type -> (pos_mode, pos_vertical, industry that runs it)
TYPES = (
    ("Restaurant", "restaurant", "restaurant", "restaurant"),
    ("Cafe", "restaurant", "cafe", "restaurant"),
    ("Supermarket", "retail", "supermarket", "supermarket"),
    ("General Retail", "retail", "general", "supermarket"),
)
RESTO_API = "zatgo_core.api.v1.resto_pos.tables.list"
RETAIL_API = "zatgo_core.api.v1.retail_pos.sale.create"


def _stored(doctype: str, field: str):
    rows = frappe.db.sql("select value from tabSingles where doctype = %s and field = %s", (doctype, field))
    return rows[0][0] if rows else None


def _put(doctype: str, field: str, value) -> None:
    """Store a Single's value, or remove the row so 'nothing stored' stays nothing stored."""
    frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (doctype, field))
    if value is not None:
        frappe.db.set_single_value(doctype, field, value)
    frappe.clear_document_cache(doctype, doctype)


def _industries_on() -> set[str]:
    frappe.clear_document_cache(gate.SETTINGS, gate.SETTINGS)
    return gate.enabled_keys()


class TestPosTypeEffect(IndustryTestBase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        _Base.company = cls.company
        cls.warehouse = _Base._make_warehouse("PosTypeTest")
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
        self._type_before = _stored(pos_settings.SETTINGS, "pos_type")
        self._switch_before = _stored(SYSTEM, "enable_zatgo_pos")
        _put(pos_settings.SETTINGS, "pos_type", None)
        _put(SYSTEM, "enable_zatgo_pos", 1)  # the POS app itself is on, whatever the site had

    def tearDown(self) -> None:
        _put(pos_settings.SETTINGS, "pos_type", self._type_before)
        _put(SYSTEM, "enable_zatgo_pos", self._switch_before)
        super().tearDown()
        # The services commit mid-test, which would persist the transient type / switch: commit the restored state.
        frappe.db.commit()

    # -- helpers ------------------------------------------------------------

    def _choose(self, pos_type: str):
        doc = frappe.get_doc(pos_settings.SETTINGS)
        doc.pos_type = pos_type
        doc.save()
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)
        return doc

    def _profile(self) -> dict:
        return admin.get_profile()["data"]

    def _settings(self) -> dict:
        return pos_settings_api.get()["data"]

    def _app_gate_404(self, method: str) -> bool:
        orig = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict(path=f"/api/method/{method}")
            app_gate.gate_api()
            return False
        except frappe.DoesNotExistError:
            return True
        finally:
            frappe.local.request = orig

    def _bin(self, code: str) -> float:
        return flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": self.warehouse}, "actual_qty"))

    def _dine_in_sale(self) -> tuple[str, str]:
        """Table -> order -> kitchen -> bill -> pay through the restaurant engine. Returns (invoice, item)."""
        table = _Base._make_table("Type Test Table")
        item = _Base._make_stocked_item(self.warehouse, qty=20)
        seated = resto.seat_table(table, covers=2, client_id=f"ty-seat-{random_string(8)}")
        self.assertTrue(seated["success"], seated.get("error"))
        order_id = seated["data"]["id"]
        self.assertTrue(resto.add_item(order_id, item, qty=2, rate=10)["success"])
        self.assertTrue(resto.send_order(order_id)["success"])
        self.assertTrue(resto.mark_billing(order_id)["success"])
        paid = resto.pay(order_id, "cash", f"ty-pay-{random_string(8)}")
        self.assertTrue(paid["success"], paid.get("error"))
        self.assertEqual(paid["data"]["order"]["status"], "paid")
        return frappe.db.get_value("ZG Order", order_id, "sales_invoice"), item

    def _counter_sale(self) -> tuple[str, str, str]:
        """One-step counter sale through the retail engine. Returns (invoice, payment, item)."""
        code = f"TYPE-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=10, barcode=f"BC{code}")
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        admin.adjust_stock(code, 10, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)
        res = retail.create_sale(
            [{"item_code": code, "qty": 2, "rate": 10}], "cash", f"ty-{random_string(8)}", company=self.company
        )
        self.assertTrue(res["success"], res.get("error"))
        return res["data"]["invoice"]["id"], res["data"]["payment"]["id"], code

    # -- what the POS is told -----------------------------------------------

    def test_each_type_gives_the_pos_its_mode_and_vertical(self) -> None:
        for pos_type, mode, vertical, industry in TYPES:
            with self.subTest(pos_type):
                _set_industries()  # nothing on: choosing the type must switch its industry on by itself
                self._choose(pos_type)
                self.assertIn(industry, _industries_on())
                for source in (self._profile(), self._settings()):
                    self.assertEqual((source["pos_type"], source["pos_mode"], source["pos_vertical"]), (pos_type, mode, vertical))
                profile = self._profile()
                self.assertEqual(profile["restaurant"], industry == "restaurant")
                self.assertEqual(profile["retail"], industry == "supermarket")

    def test_changing_the_type_changes_the_answer_without_any_other_step(self) -> None:
        seen = []
        for pos_type, mode, vertical, _industry in TYPES + (TYPES[0],):
            self._choose(pos_type)
            seen.append((self._profile()["pos_mode"], self._profile()["pos_vertical"]))
            self.assertEqual(seen[-1], (mode, vertical), pos_type)
        self.assertEqual(
            seen, [("restaurant", "restaurant"), ("restaurant", "cafe"), ("retail", "supermarket"), ("retail", "general"), ("restaurant", "restaurant")]
        )

    # -- which engine answers -----------------------------------------------

    def test_restaurant_and_cafe_run_the_restaurant_engine(self) -> None:
        for pos_type in ("Restaurant", "Cafe"):
            with self.subTest(pos_type):
                _set_industries()
                self._choose(pos_type)
                self.assertFalse(self._gate_404(RESTO_API), "the restaurant API must answer")
                self.assertTrue(self._gate_404(RETAIL_API), "the retail API must stay 404 until Supermarket is on")
                self.assertFalse(self._app_gate_404(RESTO_API))
                invoice, item = self._dine_in_sale()
                si = frappe.get_doc("Sales Invoice", invoice)
                self.assertEqual((si.docstatus, si.update_stock, flt(si.outstanding_amount)), (1, 1, 0))
                self.assertEqual(self._bin(item), 18, "stock went out once")

    def test_supermarket_and_general_retail_run_the_retail_engine(self) -> None:
        for pos_type in ("Supermarket", "General Retail"):
            with self.subTest(pos_type):
                _set_industries()
                self._choose(pos_type)
                self.assertFalse(self._gate_404(RETAIL_API), "the retail API must answer")
                self.assertTrue(self._gate_404(RESTO_API), "the restaurant API must stay 404 until Restaurant is on")
                self.assertFalse(self._app_gate_404(RETAIL_API))
                invoice, payment, item = self._counter_sale()
                si = frappe.get_doc("Sales Invoice", invoice)
                self.assertEqual((si.docstatus, si.update_stock, flt(si.outstanding_amount)), (1, 1, 0))
                self.assertEqual(frappe.db.get_value("Payment Entry", payment, "docstatus"), 1)
                self.assertEqual(self._bin(item), 8, "stock went out once")

    def test_the_pos_app_switch_still_closes_both_engines(self) -> None:
        self._choose("Cafe")
        _put(SYSTEM, "enable_zatgo_pos", 0)
        self.assertTrue(self._app_gate_404(RESTO_API))
        self.assertTrue(self._app_gate_404(RETAIL_API))

    # -- switching types ----------------------------------------------------

    def test_switching_type_switches_the_new_industry_on_and_keeps_the_old_one(self) -> None:
        self._choose("Restaurant")
        self.assertEqual(_industries_on(), {"restaurant"})
        self._choose("Supermarket")
        self.assertEqual(_industries_on(), {"restaurant", "supermarket"})
        self.assertEqual(self._profile()["pos_mode"], "retail")
        # both engines are reachable, the type decides which one the POS uses
        self.assertFalse(self._gate_404(RESTO_API))
        self.assertFalse(self._gate_404(RETAIL_API))
        self._choose("Cafe")
        self.assertEqual(_industries_on(), {"restaurant", "supermarket"})
        self.assertEqual((self._profile()["pos_mode"], self._profile()["pos_vertical"]), ("restaurant", "cafe"))

    def test_a_chosen_type_whose_industry_was_switched_off_leaves_the_pos_with_nothing(self) -> None:
        self._choose("Supermarket")
        _set_industries()
        profile = self._profile()
        self.assertIsNone(profile["pos_mode"])
        self.assertIsNone(profile["pos_vertical"])
        self.assertEqual(profile["pos_type"], "Supermarket", "the choice is kept, only the engine is off")

    # -- types that cannot be chosen ----------------------------------------

    def test_pharmacy_and_electrical_are_refused_and_change_nothing(self) -> None:
        self._choose("Restaurant")
        for coming in pos_settings.COMING_SOON:
            with self.subTest(coming):
                with self.assertRaises(frappe.ValidationError):
                    self._choose(coming)
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)
        self.assertEqual(self._profile()["pos_type"], "Restaurant")
        self.assertEqual(_industries_on(), {"restaurant"})

    def test_only_a_system_manager_can_change_the_type(self) -> None:
        self._choose("Restaurant")
        user = self._user("ZG Company Admin")  # may write the settings form, may not switch industries
        frappe.set_user(user)
        try:
            doc = frappe.get_doc(pos_settings.SETTINGS)
            doc.pos_type = "Supermarket"
            with self.assertRaises(frappe.PermissionError):
                doc.save()
        finally:
            frappe.set_user("Administrator")
        frappe.clear_document_cache(pos_settings.SETTINGS, pos_settings.SETTINGS)
        self.assertEqual(self._profile()["pos_type"], "Restaurant")
        self.assertEqual(_industries_on(), {"restaurant"})
