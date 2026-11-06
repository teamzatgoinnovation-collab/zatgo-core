"""Read-only mode end to end on a real site: the same site, unmanaged / trial / expired / paid, and every route a
write can take (Desk save, REST, whitelisted endpoints, a custom DocType, submit / cancel, a background job).

The platform's pushed state is simulated by setting `frappe.conf["zg_subscription"]` -- exactly what the site reads."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.services import subscription_gate as gate

CONF = gate.CONF_KEY


def _iso(delta_days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


def _push(**state) -> None:
    base = {"enforcement_on": 1, "status": "TRIAL", "trial_ends_at": _iso(20), "portal_url": "https://space.test"}
    base.update(state)
    frappe.local.conf[CONF] = base


def _pull() -> None:
    frappe.local.conf.pop(CONF, None)


def _note(title: str | None = None):
    return frappe.get_doc({"doctype": "Note", "title": title or f"t-{random_string(8)}", "content": "x"})


class TestSubscriptionGate(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        _pull()

    def tearDown(self):
        _pull()
        frappe.set_user("Administrator")
        frappe.db.rollback()

    # --- unmanaged / trial / paid: nothing is restricted --------------------------------------------------

    def test_unmanaged_site_is_never_restricted(self):
        _note().insert()
        self.assertFalse(gate.is_read_only())

    def test_running_trial_can_write_and_reports_days(self):
        _push(trial_ends_at=_iso(20, ) if False else _iso(19.5))
        _note().insert()
        info = gate.current()
        self.assertEqual(info["status"], "TRIAL")
        self.assertEqual(info["remaining_days"], 20)

    def test_active_paid_subscription_can_write_after_trial_end(self):
        _push(status="ACTIVE", trial_ends_at=_iso(-5), paid_until=_iso(25))
        _note().insert()
        self.assertFalse(gate.is_read_only())

    def test_trial_with_payment_before_status_push_can_write(self):
        _push(trial_ends_at=_iso(-1), paid_until=_iso(20))
        _note().insert()

    # --- expired: every write route is refused, reads and login-side stay open ---------------------------

    def _expire(self):
        _push(trial_ends_at=_iso(-1))

    def test_document_insert_update_delete_blocked(self):
        existing = _note().insert()
        self._expire()
        with self.assertRaises(frappe.PermissionError):
            _note().insert()
        existing.reload()
        existing.content = "changed"
        with self.assertRaises(frappe.PermissionError):
            existing.save()
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("Note", existing.name)

    def test_ignore_permissions_does_not_bypass(self):
        self._expire()
        with self.assertRaises(frappe.PermissionError):
            _note().insert(ignore_permissions=True)

    def test_other_users_and_system_manager_blocked_too(self):
        email = f"ro.{random_string(8).lower()}@zatgo.test"
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "RO", "send_welcome_email": 0,
                               "roles": [{"role": "System Manager"}]}).insert()
        self._expire()
        frappe.set_user(user.name)
        with self.assertRaises(frappe.PermissionError):
            _note().insert()
        probe = frappe.get_doc("Note", frappe.get_all("Note", limit=1, pluck="name")[0]) if frappe.db.count("Note") else None
        if probe:
            self.assertFalse(frappe.has_permission("Note", "write", doc=probe, user=user.name))
            self.assertTrue(frappe.has_permission("Note", "read", doc=probe, user=user.name))

    def test_reads_still_work(self):
        n = _note().insert()
        self._expire()
        self.assertEqual(frappe.get_doc("Note", n.name).name, n.name)
        self.assertTrue(frappe.get_all("Note", filters={"name": n.name}))
        self.assertEqual(frappe.client.get_count("Note"), frappe.db.count("Note"))

    def test_whitelisted_client_methods_blocked(self):
        existing = _note().insert()
        self._expire()
        for call in (
            lambda: frappe.client.insert({"doctype": "Note", "title": "x", "content": "y"}),
            lambda: frappe.client.set_value("Note", existing.name, "title", "z"),
            lambda: frappe.client.delete("Note", existing.name),
        ):
            with self.assertRaises(frappe.PermissionError):
                call()

    def test_custom_doctype_blocked(self):
        name = f"ZG Gate Probe {random_string(5)}"
        dt = frappe.get_doc({
            "doctype": "DocType", "name": name, "module": "Core", "custom": 1, "autoname": "hash",
            "fields": [{"fieldname": "title", "fieldtype": "Data", "label": "Title"}],
            "permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1}],
        }).insert()
        frappe.get_doc({"doctype": dt.name, "title": "ok"}).insert()
        self._expire()
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({"doctype": dt.name, "title": "blocked"}).insert()

    def test_submit_and_cancel_blocked(self):
        before = frappe.get_doc({"doctype": "ToDo", "description": "x"}).insert()
        self._expire()
        for hook in ("before_submit", "before_cancel", "before_update_after_submit"):
            self.assertIn("subscription_gate.enforce_doc_write", frappe.get_hooks("doc_events")["*"][hook][0] if isinstance(
                frappe.get_hooks("doc_events")["*"][hook], list) else frappe.get_hooks("doc_events")["*"][hook])
        with self.assertRaises(frappe.PermissionError):
            gate.enforce_doc_write(before, "before_submit")

    def test_background_job_write_blocked_and_job_wrapper_skips(self):
        self._expire()
        ran = []

        @gate.guard_job
        def job():
            ran.append(1)
            _note().insert()

        job()
        self.assertEqual(ran, [])
        with self.assertRaises(frappe.PermissionError):
            _note().insert(ignore_permissions=True)  # a job that is not wrapped still cannot write documents

    def test_exempt_log_doctypes_stay_writable(self):
        note = _note().insert()
        self._expire()
        frappe.get_doc({"doctype": "Error Log", "method": "probe", "error": "probe"}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Note",
                        "reference_name": note.name, "content": "probe"}).insert(ignore_permissions=True)

    def test_own_user_record_stays_editable_for_password_and_language(self):
        email = f"own.{random_string(8).lower()}@zatgo.test"
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Own", "send_welcome_email": 0,
                               "roles": [{"role": "System Manager"}]}).insert()
        self._expire()
        frappe.set_user(user.name)
        me = frappe.get_doc("User", user.name)
        me.language = "ar"
        me.save()
        other = frappe.get_doc("User", "Administrator")
        other.language = "ar"
        with self.assertRaises(frappe.PermissionError):
            other.save()

    def test_install_migrate_patch_context_is_not_blocked(self):
        self._expire()
        frappe.flags.in_patch = True
        try:
            _note().insert(ignore_permissions=True)
        finally:
            frappe.flags.in_patch = False

    # --- REST / request layer ----------------------------------------------------------------------------

    def _client(self):
        from frappe.tests.utils import make_test_client  # type: ignore
        return make_test_client() if False else None

    def test_request_gate_blocks_resource_writes_and_write_methods(self):
        from werkzeug.test import EnvironBuilder
        from werkzeug.wrappers import Request

        def request(path, method="POST"):
            return Request(EnvironBuilder(path=path, method=method).get_environ())

        self._expire()
        for path, method in (("/api/resource/Note", "POST"), ("/api/resource/Note/x", "PUT"),
                             ("/api/resource/Note/x", "DELETE"), ("/api/method/frappe.client.insert", "POST"),
                             ("/api/method/frappe.desk.form.save.savedocs", "POST"),
                             ("/api/method/frappe.desk.reportview.delete_items", "POST")):
            frappe.local.request = request(path, method)
            with self.assertRaises(frappe.PermissionError, msg=f"{method} {path}"):
                gate.gate_requests()
        for path, method in (("/api/resource/Note", "GET"), ("/api/method/frappe.client.get_list", "GET"),
                             ("/api/method/frappe.auth.get_logged_user", "GET"), ("/api/method/login", "POST"),
                             ("/api/method/zatgo_core.api.v1.subscription.get_status", "GET")):
            frappe.local.request = request(path, method)
            gate.gate_requests()  # must not raise

    # --- state handling ----------------------------------------------------------------------------------

    def test_state_may_be_a_json_string_and_garbage_is_ignored(self):
        frappe.local.conf[CONF] = json.dumps({"enforcement_on": 1, "status": "EXPIRED"})
        self.assertTrue(gate.is_read_only())
        frappe.local.conf[CONF] = "{not json"
        self.assertFalse(gate.is_read_only())

    def test_boot_payload_and_status_api(self):
        from zatgo_core.api.v1 import subscription
        self.assertEqual(subscription.get_status(), {"managed": False})
        self._expire()
        out = subscription.get_status()
        self.assertTrue(out["managed"])
        self.assertTrue(out["read_only"])
        self.assertEqual(out["status"], "EXPIRED")
        self.assertEqual(out["portal_url"], "https://space.test")

    def test_reactivation_by_a_new_push_restores_writes(self):
        self._expire()
        with self.assertRaises(frappe.PermissionError):
            _note().insert()
        _push(status="ACTIVE", paid_until=_iso(30))
        _note().insert()
