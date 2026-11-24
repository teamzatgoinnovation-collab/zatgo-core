"""Licence time policy: expiry, grace, perpetual, clock rollback (no database)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from zatgo_core.licensing.licence_policy import evaluate


def at(day: str, hour: int = 12) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=timezone.utc)


LICENCE = {"expiry_date": "2026-12-31", "grace_days": 5}


class TestPolicy(unittest.TestCase):
    def test_no_licence(self) -> None:
        self.assertEqual(evaluate(None, at("2026-06-01"))["state"], "none")

    def test_before_on_and_after_expiry(self) -> None:
        self.assertEqual(evaluate(LICENCE, at("2026-12-01"))["days_left"], 30)
        on = evaluate(LICENCE, at("2026-12-31", 23))
        self.assertEqual((on["state"], on["days_left"]), ("ok", 0))
        grace = evaluate(LICENCE, at("2027-01-02"))
        self.assertEqual((grace["state"], grace["reason"], grace["days_left"]), ("grace", "licence_grace", 3))
        self.assertEqual(grace["grace_ends"], "2027-01-05")
        self.assertEqual(evaluate(LICENCE, at("2027-01-05"))["state"], "grace")
        late = evaluate(LICENCE, at("2027-01-06"))
        self.assertEqual((late["state"], late["reason"]), ("read_only", "licence_expired"))

    def test_no_grace(self) -> None:
        self.assertEqual(evaluate({"expiry_date": "2026-12-31", "grace_days": 0}, at("2027-01-01"))["state"], "read_only")

    def test_perpetual_never_expires(self) -> None:
        self.assertEqual(evaluate({"expiry_date": None}, at("2099-01-01"))["state"], "ok")

    def test_clock_rollback(self) -> None:
        now = at("2026-06-01")
        self.assertEqual(evaluate(LICENCE, now, hwm=now + timedelta(hours=47))["state"], "ok")
        rolled = evaluate(LICENCE, now, hwm=now + timedelta(hours=49))
        self.assertEqual((rolled["state"], rolled["reason"]), ("read_only", "clock_rollback"))
        self.assertEqual(evaluate(LICENCE, now, hwm=now + timedelta(hours=49), tolerance_hours=72)["state"], "ok")
        self.assertEqual(evaluate({"expiry_date": None}, now, hwm=now + timedelta(days=30))["reason"], "clock_rollback")

    def test_accepts_dates_and_datetimes(self) -> None:
        self.assertEqual(evaluate({"expiry_date": at("2026-12-31"), "grace_days": None}, at("2027-01-01"))["state"],
                         "read_only")


if __name__ == "__main__":
    unittest.main()
