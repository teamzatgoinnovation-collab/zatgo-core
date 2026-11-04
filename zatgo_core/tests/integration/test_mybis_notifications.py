"""MyBis invoice alerts and the daily report against real documents: who is told, who is not, that a failing notifier never blocks a
submit, and that the report's figures and its once-a-day delivery hold. Every test rolls back."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import getdate, today

from zatgo_core.api.v1.mybis import daily, notify
from zatgo_core.services import app_state
from zatgo_core.services.mybis import daily_report, delivery, notify_prefs
from zatgo_core.tests.integration.test_mybis_analytics import _purchase, _supplier
from zatgo_core.tests.integration.test_mybis_dashboard import COMPANY, _company, _customer, _group, _invoice, _item

WATCHER = "mybis-watcher@example.com"
OTHER = "mybis-other@example.com"


# Some sites carry Custom DocPerms on Sales Invoice (VanSaleX) that leave Accounts Manager unable to read it; VanSale Admin can.
_ROLES = [r for r in ("Accounts Manager", "VanSale Admin") if frappe.db.exists("Role", r)]


def _user(email: str) -> str:
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0, "roles": [{"role": r} for r in _ROLES]}
        ).insert(ignore_permissions=True)
    return email


def _inbox(user: str) -> list[dict]:
    return frappe.get_all("Notification Log", filters={"for_user": user, "subject": ("like", delivery.TAG + "%")}, fields=["subject", "document_name"])


class TestMyBisNotifications(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        _company()
        frappe.db.commit()

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self.on = patch.object(app_state, "is_on", lambda key: True)
        self.on.start()
        self.watcher, self.other = _user(WATCHER), _user(OTHER)
        notify_prefs.save({"sales_invoice": 1, "purchase_invoice": 1, "daily_report": 1}, self.watcher)
        notify_prefs.save({"sales_invoice": 0}, self.other)
        self.cust, self.supp = _customer(), _supplier()
        self.item = _item(_group("MyBis Notify Cat"))

    def tearDown(self) -> None:
        self.on.stop()
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def test_opted_in_user_is_told_of_a_sales_invoice_and_others_are_not(self) -> None:
        name = _invoice(self.cust, self.item, 2, 100, getdate(today()))
        rows = _inbox(self.watcher)
        self.assertEqual([r["document_name"] for r in rows], [name])
        self.assertIn("Sales invoice", rows[0]["subject"])
        self.assertEqual(_inbox(self.other), [])

    def test_purchase_invoice_alert(self) -> None:
        name = _purchase(self.supp, self.item, 1, 80, getdate(today()))
        self.assertEqual([r["document_name"] for r in _inbox(self.watcher)], [name])

    def test_submitter_is_not_told_of_their_own_invoice(self) -> None:
        notify_prefs.save({"sales_invoice": 1}, "Administrator")
        _invoice(self.cust, self.item, 1, 10, getdate(today()))
        self.assertEqual(_inbox("Administrator"), [])

    def test_a_failing_notifier_never_blocks_the_submit(self) -> None:
        with patch.object(delivery, "notify", side_effect=RuntimeError("boom")):
            name = _invoice(self.cust, self.item, 1, 10, getdate(today()))
        self.assertEqual(frappe.db.get_value("Sales Invoice", name, "docstatus"), 1)

    def test_switch_off_sends_nothing(self) -> None:
        self.on.stop()
        with patch.object(app_state, "is_on", lambda key: False):
            _invoice(self.cust, self.item, 1, 10, getdate(today()))
        self.on.start()
        self.assertEqual(_inbox(self.watcher), [])

    def test_admin_limit_wins_over_the_user_choice(self) -> None:
        with patch.object(notify_prefs, "allowed", lambda: {**{k: True for k in notify_prefs.PREFS}, "sales_invoice": False}):
            self.assertEqual(notify_prefs.recipients("sales_invoice"), [])

    def test_prefs_endpoints_round_trip(self) -> None:
        frappe.set_user(self.other)
        out = notify.set_prefs('{"purchase_invoice": 1, "bogus": 1}')["data"]["prefs"]
        self.assertEqual({p["key"]: p["enabled"] for p in out}["purchase_invoice"], True)
        self.assertNotIn("bogus", {p["key"] for p in out})

    def test_inbox_and_mark_read(self) -> None:
        _invoice(self.cust, self.item, 1, 10, getdate(today()))
        frappe.set_user(self.watcher)
        self.assertEqual(notify.inbox()["data"]["unread"], 1)
        notify.mark_read()
        self.assertEqual(notify.inbox()["data"]["unread"], 0)

    def test_daily_report_matches_the_documents(self) -> None:
        day = getdate(today())
        before = daily.report(company=COMPANY, date=str(day), refresh=1)["data"]
        _invoice(self.cust, self.item, 2, 100, day)  # +200 sales, +200 receivable
        _purchase(self.supp, self.item, 1, 60, day)  # +60 purchases, +60 payable
        after = daily.report(company=COMPANY, date=str(day), refresh=1)["data"]

        def grew(*path) -> float:
            a, b = after, before
            for key in path:
                a, b = a[key], b[key]
            return round(a["value"] - b["value"], 2)

        self.assertEqual(grew("sales", "net_sales"), 200.0)
        self.assertEqual(grew("sales", "invoices"), 1)
        self.assertEqual(grew("purchases", "net_purchases"), 60.0)
        self.assertEqual(grew("receivable"), 200.0)
        self.assertEqual(grew("payable"), 60.0)
        self.assertEqual(grew("money", "received"), 0.0)

    def test_scheduled_report_is_sent_once_and_only_at_its_hour(self) -> None:
        _invoice(self.cust, self.item, 1, 10, getdate(today()))
        at_hour = datetime.combine(getdate(today()), datetime.min.time()).replace(hour=20)
        with patch("zatgo_core.zatgo_core.doctype.zg_mybis_settings.zg_mybis_settings.policy") as pol:
            pol.return_value = {"notifications": {"invoice_alerts": True, "daily_report": True, "report_hour": 20, "report_email": False}}
            self.assertEqual(daily_report.send_due(at_hour.replace(hour=9)), 0)
            first = daily_report.send_due(at_hour)
            self.assertGreaterEqual(first, 1)
            self.assertEqual(daily_report.send_due(at_hour), 0)
        subjects = [r["subject"] for r in _inbox(self.watcher)]
        self.assertTrue(any("Daily report" in s and COMPANY in s for s in subjects))
