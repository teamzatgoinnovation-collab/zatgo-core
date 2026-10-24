"""MyBis period maths (no database)."""

from __future__ import annotations

import unittest
from datetime import date

from zatgo_core.services.mybis import period

D = date


class TestResolve(unittest.TestCase):
    def test_presets(self):
        t = D(2026, 10, 24)  # a Saturday
        cases = {
            "today": (t, t),
            "yesterday": (D(2026, 10, 23), D(2026, 10, 23)),
            "this_week": (D(2026, 10, 19), D(2026, 10, 25)),
            "last_week": (D(2026, 10, 12), D(2026, 10, 18)),
            "this_month": (D(2026, 10, 1), D(2026, 10, 31)),
            "last_month": (D(2026, 9, 1), D(2026, 9, 30)),
            "this_quarter": (D(2026, 10, 1), D(2026, 12, 31)),
            "last_quarter": (D(2026, 7, 1), D(2026, 9, 30)),
            "this_year": (D(2026, 1, 1), D(2026, 12, 31)),
            "last_year": (D(2025, 1, 1), D(2025, 12, 31)),
        }
        for preset, (a, b) in cases.items():
            p = period.resolve(preset, t)
            self.assertEqual((p.from_date, p.to_date), (a, b), preset)

    def test_sunday_week_start(self):
        p = period.resolve("this_week", D(2026, 10, 24), week_start=6)
        self.assertEqual((p.from_date, p.to_date), (D(2026, 10, 18), D(2026, 10, 24)))

    def test_year_rollover(self):
        t = D(2026, 1, 15)
        self.assertEqual(period.resolve("last_month", t).from_date, D(2025, 12, 1))
        q = period.resolve("last_quarter", t)
        self.assertEqual((q.from_date, q.to_date), (D(2025, 10, 1), D(2025, 12, 31)))

    def test_leap_february(self):
        self.assertEqual(period.resolve("this_month", D(2028, 2, 10)).to_date, D(2028, 2, 29))

    def test_custom(self):
        p = period.resolve("custom", D(2026, 10, 24), from_date=D(2026, 10, 1), to_date=D(2026, 10, 10))
        self.assertEqual(p.days, 10)
        with self.assertRaises(ValueError):
            period.resolve("custom", D(2026, 10, 24), from_date=D(2026, 10, 10), to_date=D(2026, 10, 1))
        with self.assertRaises(ValueError):
            period.resolve("custom", D(2026, 10, 24))
        with self.assertRaises(ValueError):
            period.resolve("nope", D(2026, 10, 24))


class TestPrevious(unittest.TestCase):
    def test_month_compares_with_previous_calendar_month(self):
        cur = period.resolve("this_month", D(2026, 3, 31))
        prev = period.previous("this_month", cur)
        self.assertEqual((prev.from_date, prev.to_date), (D(2026, 2, 1), D(2026, 2, 28)))

    def test_quarter_and_year(self):
        cur = period.resolve("this_quarter", D(2026, 2, 1))
        prev = period.previous("this_quarter", cur)
        self.assertEqual((prev.from_date, prev.to_date), (D(2025, 10, 1), D(2025, 12, 31)))
        cur = period.resolve("this_year", D(2026, 5, 5))
        prev = period.previous("this_year", cur)
        self.assertEqual((prev.from_date, prev.to_date), (D(2025, 1, 1), D(2025, 12, 31)))

    def test_custom_uses_same_length_before(self):
        cur = period.Period(D(2026, 10, 11), D(2026, 10, 20))
        prev = period.previous("custom", cur)
        self.assertEqual((prev.from_date, prev.to_date), (D(2026, 10, 1), D(2026, 10, 10)))
        self.assertEqual(prev.days, cur.days)

    def test_day_and_week(self):
        cur = period.resolve("this_week", D(2026, 10, 24))
        prev = period.previous("this_week", cur)
        self.assertEqual((prev.from_date, prev.to_date), (D(2026, 10, 12), D(2026, 10, 18)))


class TestGrowth(unittest.TestCase):
    def test_growth(self):
        self.assertEqual(period.growth_percent(125000, 110000), 13.64)
        self.assertEqual(period.growth_percent(50, 100), -50.0)
        self.assertIsNone(period.growth_percent(10, 0))
        self.assertEqual(period.growth_percent(-50, -100), 50.0)
        self.assertEqual(period.growth_percent(0, 100), -100.0)


if __name__ == "__main__":
    unittest.main()
