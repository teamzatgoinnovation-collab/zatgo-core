"""MyBis figure shape and series helpers (no database)."""

from __future__ import annotations

import unittest
from datetime import date

from zatgo_core.services.mybis import metrics


class TestMetric(unittest.TestCase):
    def test_growth_and_change(self):
        m = metrics.metric(125000, 110000)
        self.assertEqual(m["growth_percent"], 13.64)
        self.assertEqual(m["change"], 15000)
        self.assertTrue(m["higher_is_better"])

    def test_no_base_is_not_a_growth_figure(self):
        self.assertIsNone(metrics.metric(10, 0)["growth_percent"])
        m = metrics.metric(10, None)
        self.assertIsNone(m["growth_percent"])
        self.assertIsNone(m["previous_value"])

    def test_extras_and_direction(self):
        m = metrics.metric(5, 4, higher_is_better=False, basis="gl")
        self.assertFalse(m["higher_is_better"])
        self.assertEqual(m["basis"], "gl")

    def test_percent(self):
        self.assertEqual(metrics.percent(30, 120), 25.0)
        self.assertIsNone(metrics.percent(30, 0))
        self.assertIsNone(metrics.percent(None, 10))


class TestSeries(unittest.TestCase):
    def test_auto_bucket(self):
        self.assertEqual(metrics.auto_bucket(31), "day")
        self.assertEqual(metrics.auto_bucket(90), "week")
        self.assertEqual(metrics.auto_bucket(365), "week")
        self.assertEqual(metrics.auto_bucket(800), "month")

    def test_day_series_fills_gaps_with_zero(self):
        out = metrics.fill_series({date(2026, 10, 2): 5.0}, date(2026, 10, 1), date(2026, 10, 3), "day")
        self.assertEqual([p["value"] for p in out], [0.0, 5.0, 0.0])
        self.assertEqual(out[0]["date"], "2026-10-01")

    def test_week_series_starts_on_monday(self):
        out = metrics.fill_series({}, date(2026, 10, 7), date(2026, 10, 21), "week")  # Wed .. Wed
        self.assertEqual([p["date"] for p in out], ["2026-10-05", "2026-10-12", "2026-10-19"])

    def test_month_series_rolls_the_year(self):
        out = metrics.fill_series({}, date(2026, 11, 15), date(2027, 1, 10), "month")
        self.assertEqual([p["date"] for p in out], ["2026-11-01", "2026-12-01", "2027-01-01"])


if __name__ == "__main__":
    unittest.main()
