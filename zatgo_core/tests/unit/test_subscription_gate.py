"""Subscription gate: the pure evaluation (trial countdown, expiry, paid, grace, timezone) and the write-endpoint list."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from zatgo_core.services import subscription_gate as gate

UTC = timezone.utc
T0 = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def state(**kw):
    base = {"enforcement_on": 1, "status": "TRIAL", "trial_ends_at": (T0 + timedelta(days=30)).isoformat()}
    base.update(kw)
    return base


class TestEvaluate(unittest.TestCase):
    def test_no_state_is_unmanaged_and_open(self):
        for s in (None, {}, {"status": "TRIAL"}, {"enforcement_on": 0, "status": "EXPIRED"}):
            r = gate.evaluate(s, T0)
            self.assertFalse(r["managed"])
            self.assertFalse(r["read_only"])

    def test_trial_countdown_rounds_up(self):
        self.assertEqual(gate.evaluate(state(), T0)["remaining_days"], 30)
        self.assertEqual(gate.evaluate(state(), T0 + timedelta(hours=1))["remaining_days"], 30)
        self.assertEqual(gate.evaluate(state(), T0 + timedelta(days=29, hours=23))["remaining_days"], 1)
        self.assertEqual(gate.evaluate(state(), T0 + timedelta(days=29, hours=23, minutes=59))["remaining_days"], 1)
        self.assertFalse(gate.evaluate(state(), T0 + timedelta(days=29, hours=23))["read_only"])

    def test_trial_expires_exactly_at_end(self):
        end = T0 + timedelta(days=30)
        self.assertFalse(gate.evaluate(state(), end - timedelta(seconds=1))["read_only"])
        r = gate.evaluate(state(), end)
        self.assertTrue(r["read_only"])
        self.assertEqual(r["status"], "EXPIRED")
        self.assertEqual(r["remaining_days"], 0)

    def test_paid_trial_is_not_read_only(self):
        s = state(paid_until=(T0 + timedelta(days=60)).isoformat())
        self.assertFalse(gate.evaluate(s, T0 + timedelta(days=40))["read_only"])

    def test_active_paid_is_open_until_grace_ends(self):
        paid_until = T0 + timedelta(days=10)
        s = {"enforcement_on": 1, "status": "ACTIVE", "paid_until": paid_until.isoformat()}
        self.assertFalse(gate.evaluate(s, paid_until + timedelta(days=2))["read_only"])
        self.assertTrue(gate.evaluate(s, paid_until + timedelta(days=3, seconds=1))["read_only"])

    def test_read_only_statuses(self):
        for status in ("EXPIRED", "SUSPENDED", "PENDING_PAYMENT", "DELETION_SCHEDULED", "DELETED"):
            self.assertTrue(gate.evaluate({"enforcement_on": 1, "status": status}, T0)["read_only"], status)

    def test_unknown_status_never_locks_out(self):
        self.assertFalse(gate.evaluate({"enforcement_on": 1, "status": "SOMETHING_NEW"}, T0)["read_only"])

    def test_timezone_offsets_are_normalised(self):
        # 2026-12-06 15:00 in Riyadh (+03:00) is 12:00 UTC: the same instant as T0 + 30 days.
        riyadh = {"enforcement_on": 1, "status": "TRIAL", "trial_ends_at": "2026-12-06T15:00:00+03:00"}
        self.assertEqual(gate.evaluate(riyadh, T0)["remaining_days"], 30)
        self.assertTrue(gate.evaluate(riyadh, T0 + timedelta(days=30))["read_only"])
        naive = {"enforcement_on": 1, "status": "TRIAL", "trial_ends_at": "2026-12-06T12:00:00"}  # read as UTC
        self.assertTrue(gate.evaluate(naive, T0 + timedelta(days=30))["read_only"])
        z = {"enforcement_on": 1, "status": "TRIAL", "trial_ends_at": "2026-12-06T12:00:00Z"}
        self.assertTrue(gate.evaluate(z, T0 + timedelta(days=30))["read_only"])

    def test_garbage_dates_do_not_crash_or_lock(self):
        r = gate.evaluate({"enforcement_on": 1, "status": "TRIAL", "trial_ends_at": "not a date"}, T0)
        self.assertFalse(r["read_only"])


class TestWriteMethods(unittest.TestCase):
    def test_writes_listed_reads_not(self):
        for m in ("frappe.client.insert", "frappe.client.set_value", "frappe.desk.form.save.savedocs",
                  "frappe.desk.reportview.delete_items", "frappe.core.doctype.data_import.data_import.start_import",
                  "frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs", "upload_file",
                  "frappe.model.workflow.apply_workflow"):
            self.assertTrue(gate.is_write_method(m), m)
        for m in ("frappe.client.get", "frappe.client.get_list", "frappe.desk.query_report.run",
                  "frappe.desk.form.load.getdoc", "frappe.auth.get_logged_user", None, ""):
            self.assertFalse(gate.is_write_method(m), m)


if __name__ == "__main__":
    unittest.main()
