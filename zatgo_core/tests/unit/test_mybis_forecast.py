"""MyBis forecast engines (pure arithmetic, no database)."""

from __future__ import annotations

import unittest

from zatgo_core.services.mybis import forecast as fc


def weekly(n: int, base: float = 100.0, weekend: float = 2.0) -> list[float]:
    """n days starting on a Monday: weekdays = base, Sat/Sun = base * weekend."""
    return [base * (weekend if i % 7 in (5, 6) else 1.0) for i in range(n)]


class TestEngines(unittest.TestCase):
    def test_moving_average_is_the_mean_of_the_last_window(self):
        r = fc.run(list(range(1, 15)), 3, method="moving_average", window=7)  # 1..14 -> last 7 = 8..14
        self.assertEqual(r.values, [11.0, 11.0, 11.0])
        self.assertEqual(r.method, "moving_average")
        self.assertEqual(r.params, {"window": 7})

    def test_weighted_moving_average_weighs_recent_points_more(self):
        wma = fc.WeightedMovingAverage(3)
        self.assertAlmostEqual(wma.forecast([1, 2, 3], 1)[0], (1 * 1 + 2 * 2 + 3 * 3) / 6)
        self.assertGreater(wma.forecast([1, 2, 3], 1)[0], fc.MovingAverage(3).forecast([1, 2, 3], 1)[0])

    def test_constant_history_forecasts_the_constant_with_a_zero_width_range(self):
        for m in fc.ENGINES:
            r = fc.run([50.0] * 30, 5, method=m)
            self.assertEqual(r.values, [50.0] * 5, m)
            self.assertEqual((r.lower, r.upper), (r.values, r.values), m)

    def test_exponential_smoothing_reacts_to_a_level_shift(self):
        y = [10.0] * 20 + [30.0] * 20
        r = fc.run(y, 3, method="exponential_smoothing")
        self.assertGreater(r.values[0], 25.0)  # moved most of the way to the new level
        self.assertLessEqual(r.values[0], 30.0)
        self.assertGreater(r.params["alpha"], 0.5)  # a shift calls for a fast alpha

    def test_holt_continues_a_linear_trend(self):
        y = [10.0 * t + 5 for t in range(40)]
        r = fc.run(y, 5, method="holt")
        expected = [10.0 * t + 5 for t in range(40, 45)]
        for got, want in zip(r.values, expected):
            self.assertAlmostEqual(got / want, 1.0, delta=0.03)
        self.assertLess(r.wape, 0.05)

    def test_auto_picks_the_trend_engine_for_a_trend_and_reports_every_candidate(self):
        r = fc.run([10.0 * t + 5 for t in range(40)], 5, method="auto")
        self.assertEqual(r.method, "holt")
        self.assertEqual({c["method"] for c in r.candidates}, set(fc.ENGINES))
        self.assertEqual(r.candidates[-1]["method"], "holt")
        best = min(c["wape"] for c in r.candidates)
        self.assertEqual(next(c for c in r.candidates if c["method"] == r.method)["wape"], best)

    def test_results_are_deterministic(self):
        y = [float((i * 37) % 11 + 5) for i in range(60)]
        a, b = fc.run(y, 7), fc.run(y, 7)
        self.assertEqual((a.values, a.lower, a.upper, a.method), (b.values, b.lower, b.upper, b.method))


class TestSeasonality(unittest.TestCase):
    def test_weekday_pattern_is_detected_and_applied(self):
        y = weekly(56)
        idx = fc.seasonal_indices(y, 7, 0)
        self.assertIsNotNone(idx)
        self.assertAlmostEqual(sum(idx) / 7, 1.0)
        self.assertGreater(idx[5], idx[0])
        r = fc.run(y, 7, method="moving_average", period=7, offset=0)  # next 7 days: Mon..Sun again
        self.assertIsNotNone(r.seasonal)
        for i, v in enumerate(r.values):
            self.assertAlmostEqual(v, 200.0 if i in (5, 6) else 100.0, delta=1.0)

    def test_offset_aligns_the_cycle(self):
        y = weekly(56)[2:]  # starts on a Wednesday: y[0] is cycle position 2
        r = fc.run(y, 7, method="moving_average", period=7, offset=2)
        # history length 54 starting Wed -> next day is cycle position (2 + 54) % 7 = 0 (Monday)
        self.assertAlmostEqual(r.values[0], 100.0, delta=1.0)
        self.assertAlmostEqual(r.values[5], 200.0, delta=1.0)

    def test_no_pattern_no_seasonality_and_it_says_so(self):
        r = fc.run([100.0] * 56, 7, period=7)
        self.assertIsNone(r.seasonal)
        self.assertTrue(any("seasonal" in s.lower() or "pattern" in s.lower() for s in r.limitations))

    def test_less_than_two_cycles_is_not_enough(self):
        self.assertIsNone(fc.seasonal_indices(weekly(13), 7))
        self.assertIsNone(fc.seasonal_indices([0.0] * 30, 7))  # no volume


class TestRangeAndConfidence(unittest.TestCase):
    NOISY = [float(100 + ((i * 7919) % 41) - 20) for i in range(90)]

    def test_range_brackets_the_forecast_and_widens_with_the_horizon(self):
        for m in ("exponential_smoothing", "holt", "moving_average"):
            r = fc.run(self.NOISY, 30, method=m)
            for v, lo, hi in zip(r.values, r.lower, r.upper):
                self.assertLessEqual(lo, v)
                self.assertGreaterEqual(hi, v)
            self.assertGreaterEqual(r.upper[-1] - r.lower[-1], r.upper[0] - r.lower[0])
        self.assertGreater(fc.run(self.NOISY, 30, method="holt").sigma, 0)

    def test_floor_stops_negative_sales_but_not_cash_movement(self):
        falling = [100.0 - 4 * t for t in range(30)]  # heading below zero
        self.assertTrue(all(v >= 0 for v in fc.run(falling, 20, method="holt", floor=0.0).values))
        self.assertTrue(any(v < 0 for v in fc.run(falling, 20, method="holt", floor=None).values))

    def test_confidence_label(self):
        self.assertEqual(fc.confidence_label(100, 0.2), "high")
        self.assertEqual(fc.confidence_label(100, 0.5), "medium")
        self.assertEqual(fc.confidence_label(100, 0.9), "low")
        self.assertEqual(fc.confidence_label(40, 0.2), "medium")  # not enough history for "high"
        self.assertEqual(fc.confidence_label(10, 0.1), "low")
        self.assertEqual(fc.confidence_label(100, None), "low")

    def test_short_and_empty_histories_are_flagged(self):
        r = fc.run([10.0] * 10, 3)
        self.assertEqual(r.confidence, "low")
        self.assertTrue(any("data points" in s for s in r.limitations))
        z = fc.run([0.0] * 30, 5)
        self.assertEqual(z.values, [0.0] * 5)
        self.assertTrue(any("no activity" in s.lower() for s in z.limitations))
        self.assertEqual(z.confidence, "low")

    def test_every_result_says_it_is_extrapolation(self):
        r = fc.run(self.NOISY, 7)
        self.assertTrue(any("cannot anticipate" in s for s in r.limitations))

    def test_a_long_horizon_is_flagged(self):
        r = fc.run(self.NOISY[:30], 25)
        self.assertTrue(any("further ahead" in s for s in r.limitations))


class TestInputs(unittest.TestCase):
    def test_rejects_bad_input(self):
        with self.assertRaises(fc.InsufficientHistory):
            fc.run([1.0] * 5, 3)
        with self.assertRaises(ValueError):
            fc.run([1.0] * 30, 3, method="neural_net")
        with self.assertRaises(ValueError):
            fc.run([1.0] * 30, 0)
        self.assertTrue(issubclass(fc.InsufficientHistory, ValueError))

    def test_monthly_style_run_with_a_short_window(self):
        y = [1000.0 + 50 * i for i in range(18)]
        r = fc.run(y, 12, window=3, period=12, min_history=6, cycle_name="year")
        self.assertEqual(len(r.values), 12)
        self.assertIsNone(r.seasonal)  # 18 months is less than two full years


if __name__ == "__main__":
    unittest.main()
