"""Offline counter sales: a sale the POS made without a connection reaches the server late and is posted on its own date and time;
what no longer matches (price, tax, stock, item, discount cap) is posted at the server's figures and listed for review
(ZG Offline Sale Issue); a replay posts nothing twice; an unsafe sale is refused. Also the delta feeds the offline POS refreshes
its copy of the catalog from, and the settings that govern it."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import frappe
from frappe.utils import flt, now_datetime, random_string

from zatgo_core.services import offline_sale, pos_settings
from zatgo_core.services import resto_pos_admin_service as admin
from zatgo_core.services import retail_pos_service as retail
from zatgo_core.services.erpnext_reads import list_items
from zatgo_core.tests.integration._fixtures import (
    get_or_create_cash_mode_of_payment,
    get_or_create_test_company,
)
from zatgo_core.tests.integration.test_industries import IndustryTestBase
from zatgo_core.tests.integration.test_resto_pos_order_to_payment import (
    TestRestoPosOrderToPayment as _Base,
)

POS = pos_settings.SETTINGS
FIELDS = ("offline_enabled", "max_offline_hours", "max_pending_sales", "allow_card_offline", "allow_discounts", "max_discount_percent")


def _stored(field: str):
    rows = frappe.db.sql("select value from tabSingles where doctype = %s and field = %s", (POS, field))
    return rows[0][0] if rows else None


def _put(field: str, value) -> None:
    frappe.db.sql("delete from tabSingles where doctype = %s and field = %s", (POS, field))
    if value is not None:
        frappe.db.set_single_value(POS, field, value)
    frappe.clear_document_cache(POS, POS)


def _iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%S")


class TestOfflineSale(IndustryTestBase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company = get_or_create_test_company()
        _Base.company = cls.company
        cls.warehouse = _Base._make_warehouse("OfflineSaleTest")
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
        self._before = {f: _stored(f) for f in FIELDS}
        _put("offline_enabled", 1)
        _put("max_offline_hours", 72)
        _put("allow_card_offline", 0)
        _put("allow_discounts", 1)
        _put("max_discount_percent", 100)

    def tearDown(self) -> None:
        for field, value in self._before.items():
            _put(field, value)
        super().tearDown()
        frappe.db.commit()  # the services commit mid-test: persist the restored settings, not the test's

    # -- helpers ------------------------------------------------------------

    def _item(self, qty: float = 10, price: float = 10, barcode: bool = False) -> str:
        code = f"OFFLINE-{random_string(6).upper()}"
        admin.upsert_item(item_code=code, item_name=code, price=price, barcode=f"BC{code}" if barcode else None)
        frappe.db.set_value("Item", code, "valuation_rate", 5)
        if qty:
            admin.adjust_stock(code, qty, f"adj-{random_string(8)}", warehouse=self.warehouse, company=self.company)
        return code

    def _bin(self, code: str) -> float:
        return flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": self.warehouse}, "actual_qty"))

    def _hours_ago(self, hours: float) -> dt.datetime:
        return (now_datetime() - dt.timedelta(hours=hours)).replace(microsecond=0)

    def _sale(self, code: str, qty: float = 2, rate: float = 10, cid: str | None = None, **kw):
        method = kw.pop("method", "cash")
        return retail.create_sale(
            [{"item_code": code, "qty": qty, "rate": rate}],
            method,
            cid or f"off-{random_string(8)}",
            company=self.company,
            **kw,
        )

    def _offline(self, code: str, when: dt.datetime | None = None, **kw):
        when = when or self._hours_ago(20)
        return self._sale(
            code,
            offline=1,
            sale_datetime=_iso(when),
            offline_ref=kw.pop("offline_ref", f"OFF-T1-{random_string(4).upper()}"),
            device_id=kw.pop("device_id", "terminal-1"),
            **kw,
        )

    def _issue(self, cid: str):
        name = frappe.db.get_value("ZG Offline Sale Issue", {"client_id": cid}, "name")
        return frappe.get_doc("ZG Offline Sale Issue", name) if name else None

    # -- posting a late sale ------------------------------------------------

    def test_a_late_sale_keeps_its_own_date_and_time_and_receipt_number(self) -> None:
        code = self._item()
        when = self._hours_ago(20)
        cid = f"off-{random_string(8)}"
        res = self._offline(code, when, cid=cid, offline_ref="OFF-T1-0007")
        self.assertTrue(res["success"], res.get("error"))
        si = frappe.get_doc("Sales Invoice", res["data"]["invoice"]["id"])
        self.assertEqual((si.docstatus, si.update_stock, flt(si.outstanding_amount)), (1, 1, 0))
        self.assertEqual(str(si.posting_date), str(when.date()))
        self.assertEqual(str(frappe.utils.get_time(si.posting_time)), when.strftime("%H:%M:%S"))
        self.assertEqual(si.zg_offline_receipt, "OFF-T1-0007")
        pe = frappe.get_doc("Payment Entry", res["data"]["payment"]["id"])
        self.assertEqual((pe.docstatus, str(pe.posting_date)), (1, str(when.date())))
        self.assertEqual(self._bin(code), 8)
        self.assertEqual(res["meta"]["offline"], {"review": False, "issues": []}, "nothing differs, nothing to review")
        self.assertIsNone(self._issue(cid))

    def test_a_replay_returns_the_first_result_and_posts_nothing_twice(self) -> None:
        code = self._item()
        cid = f"off-{random_string(8)}"
        first = self._offline(code, cid=cid)
        again = self._offline(code, cid=cid)
        self.assertTrue(again["meta"]["idempotent"])
        self.assertEqual(first["data"]["invoice"]["id"], again["data"]["invoice"]["id"])
        self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid}), 1)
        self.assertEqual(frappe.db.count("Payment Entry", {"zatgo_client_id": f"{cid}:pay"}), 1)
        self.assertEqual(self._bin(code), 8, "stock moved once")

    def test_a_replay_with_another_price_is_refused(self) -> None:
        code = self._item()
        cid = f"off-{random_string(8)}"
        self._offline(code, cid=cid)
        with self.assertRaises(frappe.ValidationError):
            self._offline(code, cid=cid, rate=9)

    def test_an_online_sale_is_exactly_what_it_was(self) -> None:
        code = self._item()
        res = self._sale(code)
        si = frappe.get_doc("Sales Invoice", res["data"]["invoice"]["id"])
        self.assertEqual(str(si.posting_date), frappe.utils.today())
        self.assertFalse(si.zg_offline_receipt)
        self.assertNotIn("offline", res["meta"])

    # -- refusals -----------------------------------------------------------

    def test_a_site_that_did_not_switch_offline_on_refuses(self) -> None:
        _put("offline_enabled", 0)
        with self.assertRaises(frappe.ValidationError):
            self._offline(self._item())

    def test_a_time_in_the_future_or_older_than_the_limit_is_refused(self) -> None:
        code = self._item()
        with self.assertRaises(frappe.ValidationError):
            self._offline(code, now_datetime() + dt.timedelta(hours=2))
        _put("max_offline_hours", 24)
        with self.assertRaises(frappe.ValidationError):
            self._offline(code, now_datetime() - dt.timedelta(hours=24 + offline_sale.GRACE_HOURS + 2))
        self.assertEqual(self._bin(code), 10, "nothing was posted")

    def test_only_cash_offline_unless_the_site_allows_card(self) -> None:
        code = self._item()
        with self.assertRaises(frappe.ValidationError):
            self._offline(code, method="card")
        self.assertEqual(self._bin(code), 10, "nothing was posted")
        sale = offline_sale.parse(1, _iso(self._hours_ago(1)), "R", "D")
        offline_sale.check_method(sale, "cash")
        with self.assertRaises(frappe.ValidationError):
            offline_sale.check_method(sale, "card")
        _put("allow_card_offline", 1)
        offline_sale.check_method(sale, "card")  # allowed now

    # -- what differs is posted and flagged ----------------------------------

    def test_a_sale_that_arrives_more_than_a_day_late_is_listed(self) -> None:
        cid = f"off-{random_string(8)}"
        self._offline(self._item(), self._hours_ago(offline_sale.LATE_HOURS + 6), cid=cid)
        self.assertIn(offline_sale.LATE, self._issue(cid).issue_kinds)

    def test_a_total_that_differs_from_the_receipt_is_posted_and_listed(self) -> None:
        code = self._item()
        cid = f"off-{random_string(8)}"
        res = self._offline(code, cid=cid, expected_total=999.0)
        self.assertEqual(frappe.db.get_value("Sales Invoice", res["data"]["invoice"]["id"], "docstatus"), 1)
        self.assertTrue(res["meta"]["offline"]["review"])
        self.assertEqual([i["kind"] for i in res["meta"]["offline"]["issues"]], [offline_sale.TOTAL])
        issue = self._issue(cid)
        self.assertEqual((issue.status, issue.sales_invoice, flt(issue.expected_total)), ("Open", res["data"]["invoice"]["id"], 999.0))
        self.assertEqual(issue.cashier, frappe.session.user)
        self.assertEqual(issue.device_id, "terminal-1")
        # a replay does not open a second entry and reports the same issues
        again = self._offline(code, cid=cid, expected_total=999.0)
        self.assertEqual(frappe.db.count("ZG Offline Sale Issue", {"client_id": cid}), 1)
        self.assertEqual(again["meta"]["offline"]["issues"], res["meta"]["offline"]["issues"])

    def test_a_price_that_is_not_todays_price_is_posted_and_listed(self) -> None:
        code = self._item(price=12)
        cid = f"off-{random_string(8)}"
        res = self._offline(code, rate=10, cid=cid)  # sold at 10 while the list price is now 12
        si = frappe.get_doc("Sales Invoice", res["data"]["invoice"]["id"])
        self.assertEqual(flt(si.items[0].rate), 10)
        self.assertIn(offline_sale.PRICE, self._issue(cid).issue_kinds)

    def test_short_stock_posts_negative_for_this_invoice_only_and_is_listed(self) -> None:
        code = self._item(qty=1)
        cid = f"off-{random_string(8)}"
        res = self._offline(code, qty=3, cid=cid)
        self.assertEqual(frappe.db.get_value("Sales Invoice", res["data"]["invoice"]["id"], "docstatus"), 1)
        self.assertEqual(self._bin(code), -2)
        self.assertIn(offline_sale.STOCK, self._issue(cid).issue_kinds)
        # the exception is this invoice's: the site setting is untouched, so the next sale is refused again
        if not frappe.db.get_single_value("Stock Settings", "allow_negative_stock"):
            with self.assertRaises(frappe.ValidationError):
                self._sale(code, qty=1)

    def test_a_discount_over_the_cap_is_refused_online_and_listed_offline(self) -> None:
        _put("max_discount_percent", 10)
        code = self._item()
        with self.assertRaises(frappe.ValidationError):
            self._sale(code, discount_type="percent", discount_value=20)
        cid = f"off-{random_string(8)}"
        self._offline(code, cid=cid, discount_type="percent", discount_value=20)
        self.assertIn(offline_sale.DISCOUNT, self._issue(cid).issue_kinds)
        self.assertTrue(self._sale(code, discount_type="percent", discount_value=10)["success"], "inside the cap is fine")

    def test_discounts_switched_off_refuse_any_discount_online(self) -> None:
        _put("allow_discounts", 0)
        with self.assertRaises(frappe.ValidationError):
            self._sale(self._item(), discount_type="percent", discount_value=5)

    def test_an_item_disabled_meanwhile_cannot_be_posted_and_is_refused_with_its_reason(self) -> None:
        code = self._item()
        frappe.db.set_value("Item", code, "disabled", 1)
        cid = f"off-{random_string(8)}"
        with self.assertRaises(frappe.ValidationError) as ctx:
            self._offline(code, cid=cid)
        self.assertIn("disabled", str(ctx.exception))
        self.assertFalse(frappe.db.exists("Sales Invoice", {"zatgo_client_id": cid}))
        self.assertEqual(self._bin(code), 10)

    def test_a_posted_sale_still_replays_after_its_item_was_disabled(self) -> None:
        code = self._item()
        cid = f"off-{random_string(8)}"
        first = self._offline(code, cid=cid)
        frappe.db.set_value("Item", code, "disabled", 1)
        again = self._offline(code, cid=cid)
        self.assertEqual(first["data"]["invoice"]["id"], again["data"]["invoice"]["id"])

    # -- a failed payment step is pending, not failed ------------------------

    def test_a_failed_payment_step_is_a_503_and_the_same_id_completes_it(self) -> None:
        code = self._item()
        cid = f"off-{random_string(8)}"
        from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry

        with patch.object(PaymentEntry, "submit", side_effect=RuntimeError("boom")):
            with self.assertRaises(offline_sale.PaymentPendingError) as ctx:
                self._offline(code, cid=cid)
        self.assertEqual(ctx.exception.http_status_code, 503)
        self.assertEqual(frappe.db.get_value("Sales Invoice", {"zatgo_client_id": cid}, "docstatus"), 1, "the invoice stayed posted")
        done = self._offline(code, cid=cid)
        self.assertEqual(frappe.db.count("Sales Invoice", {"zatgo_client_id": cid}), 1)
        self.assertEqual(frappe.db.get_value("Payment Entry", done["data"]["payment"]["id"], "docstatus"), 1)

    # -- the feeds the offline copy is refreshed from ------------------------

    def test_the_catalog_delta_lists_changes_and_what_was_switched_off(self) -> None:
        kept = self._item(barcode=True)
        gone = self._item()
        since = (now_datetime() - dt.timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        frappe.db.set_value("Item", gone, "disabled", 1)  # modified now
        frappe.db.set_value("Item", kept, "item_name", "Renamed offline item")
        plain = {r["item_code"] for r in list_items(page=1, page_size=100, modified_since=since)["data"]}
        self.assertIn(kept, plain)
        self.assertNotIn(gone, plain, "disabled items are not listed unless asked for")
        full = {r["item_code"]: r for r in list_items(page=1, page_size=100, modified_since=since, include_disabled=1)["data"]}
        self.assertEqual(int(full[gone]["disabled"]), 1)
        self.assertEqual(full[kept]["barcode"], f"BC{kept}")
        none_since_future = list_items(page=1, page_size=100, modified_since="2999-01-01 00:00:00", include_disabled=1)["data"]
        self.assertEqual(none_since_future, [])

    def test_the_customer_delta_lists_changes_and_what_was_switched_off(self) -> None:
        name = f"Offline Feed {random_string(5)}"
        made = admin.upsert_customer(None, name, "0500000009", None, f"cust-{random_string(8)}")["data"]["id"]
        since = (now_datetime() - dt.timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        frappe.db.set_value("Customer", made, "disabled", 1)
        plain = {r["id"] for r in admin.list_customers(None, 1, 100, since)["data"]}
        self.assertNotIn(made, plain)
        full = {r["id"]: r for r in admin.list_customers(None, 1, 100, since, 1)["data"]}
        self.assertEqual(full[made]["disabled"], 1)

    def test_the_profile_carries_a_tax_version_that_follows_the_tax(self) -> None:
        a = admin._tax_version({"tax_template": "T", "tax_rate": 15, "tax_inclusive": 0})
        self.assertEqual(a, admin._tax_version({"tax_template": "T", "tax_rate": 15, "tax_inclusive": 0}))
        self.assertNotEqual(a, admin._tax_version({"tax_template": "T", "tax_rate": 5, "tax_inclusive": 0}))
        self.assertNotEqual(a, admin._tax_version({"tax_template": "T", "tax_rate": 15, "tax_inclusive": 1}))
        self.assertIn("tax_version", admin.get_profile()["data"])

    # -- the settings that govern it ------------------------------------------

    def test_the_offline_policy_is_served_with_its_defaults_and_is_off_unless_switched_on(self) -> None:
        for field in FIELDS[:4]:
            _put(field, None)
        policy = pos_settings.effective()["offline"]
        self.assertEqual(
            policy,
            {"enabled": 0, "max_offline_hours": 72, "max_pending_sales": 500, "snapshot_refresh_minutes": 15, "allow_card_offline": 0},
        )

    def test_a_never_saved_form_still_allows_discounts_up_to_100_percent(self) -> None:
        _put("allow_discounts", None)
        _put("max_discount_percent", None)
        self.assertEqual(pos_settings.discount_policy(), (1, 100.0))
        self.assertTrue(self._sale(self._item(), discount_type="percent", discount_value=50)["success"])

    def test_offline_limits_must_be_sensible(self) -> None:
        doc = frappe.get_doc(POS)
        doc.max_offline_hours = 100000
        with self.assertRaises(frappe.ValidationError):
            doc.save()
