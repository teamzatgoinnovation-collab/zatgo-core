"""Regression tests for the 2026-10-19 audit fixes: Space guest endpoints,
Tracker demo passwords, device-token takeover, query-report parameter forwarding."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1 import devices
from zatgo_core.overrides import query_report
from zatgo_core.zatgo_space.api.v1 import space


class TestSpaceGuestEndpoints(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self.slug = f"zgt{random_string(6).lower()}"
        if not frappe.db.exists("Space Plan", "basic"):
            frappe.get_doc(
                {"doctype": "Space Plan", "code": "basic", "title": "Basic", "mock_price": "0", "is_active": 1}
            ).insert(ignore_permissions=True)
        self.order = frappe.get_doc(
            {
                "doctype": "Space Order",
                "slug": self.slug,
                "hostname": f"{self.slug}.example.test",
                "status": "Active",
                "plan": "basic",
                "desk_url": f"https://{self.slug}.example.test",
                "job_id": "job-secret-123",
                "error_message": "internal path /srv/bench failed",
                "ram_used_mb": 321,
            }
        ).insert(ignore_permissions=True)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.delete_doc("Space Order", self.order.name, force=True, ignore_permissions=True)

    def test_guest_gets_no_site_list(self) -> None:
        frappe.set_user("Guest")
        data = space.list_sites_usage()["data"]
        self.assertEqual(data["sites"], [])
        self.assertIn("pool", data)

    def test_staff_gets_site_list(self) -> None:
        names = [s["name"] for s in space.list_sites_usage()["data"]["sites"]]
        self.assertIn(self.order.name, names)

    def test_guest_get_order_hides_internals(self) -> None:
        frappe.set_user("Guest")
        data = space.get_order(name=self.order.name)["data"]
        self.assertEqual(data["status"], "Active")
        for hidden in ("jobId", "error", "ramUsedMb", "diskUsedMb", "ramLimitMb"):
            self.assertNotIn(hidden, data)
        for entry in data["logs"]:
            self.assertNotIn("message", entry)

    def test_staff_get_order_has_full_detail(self) -> None:
        data = space.get_order(name=self.order.name)["data"]
        self.assertEqual(data["jobId"], "job-secret-123")
        self.assertIn("error", data)
        self.assertEqual(data["ramUsedMb"], 321)

    def test_create_order_is_rate_limited(self) -> None:
        """11th request from one IP inside the hour is refused (bad slug keeps each call cheap)."""
        frappe.set_user("Guest")
        request = MagicMock(method="POST")
        ip = f"203.0.113.{random_string(3)}"
        with patch.object(frappe.local, "request", request, create=True), patch.object(
            frappe.local, "request_ip", ip, create=True
        ), patch.object(frappe.local, "form_dict", frappe._dict(cmd="zgt.rate.create_order"), create=True):
            for _ in range(10):
                self.assertFalse(space.create_order(slug="!!bad!!", plan="basic")["success"])
            with self.assertRaises(frappe.RateLimitExceededError):
                space.create_order(slug="!!bad!!", plan="basic")


class TestTrackerDemoPasswords(IntegrationTestCase):
    def test_no_fixed_password_in_source(self) -> None:
        import inspect

        from zatgo_core.tracker.setup import demo_data, demo_org

        for module in (demo_org, demo_data):
            self.assertNotIn("Tracker@123", inspect.getsource(module))

    def test_new_users_get_random_returned_passwords(self) -> None:
        from zatgo_core.tracker.setup import demo_org

        email = f"zgt-{random_string(6).lower()}@example.test"
        passwords: dict[str, str] = {}
        try:
            demo_org._ensure_user(email, "Zgt User", "Tracker Worker", passwords)
            self.assertIn(email, passwords)
            self.assertGreaterEqual(len(passwords[email]), 16)
            self.assertNotEqual(passwords[email], "Tracker@123")
            # an existing user is left alone: no new password is issued
            again: dict[str, str] = {}
            demo_org._ensure_user(email, "Zgt User", "Tracker Worker", again)
            self.assertEqual(again, {})
        finally:
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)


class TestDeviceTokenTakeover(IntegrationTestCase):
    def setUp(self) -> None:
        self.token = f"zgt-token-{random_string(10)}"
        self.owner = self._user("owner")
        self.other = self._user("other")

    def _user(self, tag: str) -> str:
        email = f"zgt-{tag}-{random_string(5).lower()}@example.test"
        frappe.get_doc(
            {"doctype": "User", "email": email, "first_name": tag, "send_welcome_email": 0, "roles": [{"role": "Employee"}]}
        ).insert(ignore_permissions=True)
        return email

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for name in frappe.get_all("ZG Device Token", filters={"token": self.token}, pluck="name"):
            frappe.delete_doc("ZG Device Token", name, force=True, ignore_permissions=True)
        for email in (self.owner, self.other):
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)

    def test_other_user_cannot_take_a_registered_token(self) -> None:
        frappe.set_user(self.owner)
        self.assertTrue(devices.register_token(self.token, "android")["success"])
        frappe.set_user(self.other)
        result = devices.register_token(self.token, "android")
        self.assertFalse(result["success"])
        frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("ZG Device Token", {"token": self.token}, "user"), self.owner)

    def test_owner_can_re_register_and_manager_can_reassign(self) -> None:
        frappe.set_user(self.owner)
        self.assertTrue(devices.register_token(self.token, "android")["success"])
        self.assertTrue(devices.register_token(self.token, "ios")["success"])
        frappe.set_user("Administrator")
        self.assertTrue(devices.register_token(self.token, "web")["success"])
        self.assertEqual(frappe.db.get_value("ZG Device Token", {"token": self.token}, "user"), "Administrator")


class TestQueryReportForwarding(IntegrationTestCase):
    def test_forward_kwargs_keeps_only_upstream_params(self) -> None:
        kept = query_report.forward_kwargs({"is_tree": 1, "user": "x", "cmd": "frappe.desk.query_report.run", "bogus": 1})
        self.assertEqual(kept, {"is_tree": 1, "user": "x"})

    def test_run_passes_new_upstream_params_through(self) -> None:
        with patch.object(query_report.frappe_query_report, "run", return_value={"ok": 1}) as upstream, patch.object(
            query_report, "_UPSTREAM_PARAMS", query_report._UPSTREAM_PARAMS | {"future_param"}
        ):
            query_report.run("General Ledger", filters={"a": 1}, future_param=7, cmd="ignored")
        upstream.assert_called_once()
        kwargs = upstream.call_args.kwargs
        self.assertEqual(kwargs["future_param"], 7)
        self.assertEqual(kwargs["report_name"], "General Ledger")
        self.assertNotIn("cmd", kwargs)
