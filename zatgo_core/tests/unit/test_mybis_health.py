"""Inventory health score arithmetic (no database)."""

from __future__ import annotations

import unittest

from zatgo_core.services.mybis import health


def score(**kw):
    base = dict(stocked_items=100, out_of_stock=0, low_stock=0, negative=0, stock_value=1000.0, dead_value=0.0, overstock_value=0.0, turnover=4.0)
    base.update(kw)
    return health.score(**base)


class TestHealth(unittest.TestCase):
    def test_weights_add_up_to_100(self):
        self.assertEqual(sum(health.WEIGHTS.values()), 100)

    def test_a_clean_position_scores_100(self):
        r = score()
        self.assertEqual(r["score"], 100)
        self.assertEqual(r["rating"], "good")
        self.assertEqual(len(r["factors"]), 6)

    def test_each_problem_costs_its_own_factor_only(self):
        r = score(out_of_stock=50)
        pts = {f["key"]: f["points"] for f in r["factors"]}
        self.assertEqual(pts["availability"], 12.5)
        self.assertEqual(pts["low_stock"], 15)
        self.assertEqual(r["score"], 88)  # 100 - 12.5

    def test_negative_stock_weighs_five_times(self):
        pts = {f["key"]: f["points"] for f in score(negative=10)["factors"]}
        self.assertEqual(pts["negative_stock"], 7.5)  # 10 items * 5 = 50% of 100 stocked items
        self.assertEqual({f["key"]: f["points"] for f in score(negative=40)["factors"]}["negative_stock"], 0)

    def test_dead_and_overstock_are_shares_of_value(self):
        r = score(dead_value=500, overstock_value=250)
        pts = {f["key"]: f["points"] for f in r["factors"]}
        self.assertEqual(pts["dead_stock"], 10)
        self.assertEqual(pts["overstock"], 7.5)

    def test_turnover(self):
        self.assertEqual({f["key"]: f["points"] for f in score(turnover=2.0)["factors"]}["turnover"], 7.5)
        none = {f["key"]: f for f in score(turnover=None)["factors"]}["turnover"]
        self.assertEqual(none["points"], 0)
        self.assertIn("No stock was sold", none["detail"])
        self.assertEqual({f["key"]: f["points"] for f in score(turnover=10)["factors"]}["turnover"], 15)

    def test_everything_wrong_floors_at_zero_and_is_poor(self):
        r = score(out_of_stock=100, low_stock=100, negative=100, dead_value=1000, overstock_value=1000, turnover=None)
        self.assertEqual(r["score"], 0)
        self.assertEqual(r["rating"], "poor")

    def test_no_stock_records_is_not_a_perfect_score(self):
        r = score(stocked_items=0, stock_value=0)
        self.assertIsNone(r["score"])
        self.assertTrue(r["note"])

    def test_rating_bands(self):
        self.assertEqual([health.rating(x) for x in (100, 80, 79, 60, 59, 0)], ["good", "good", "fair", "fair", "poor", "poor"])

    def test_wording_agrees_with_the_count(self):
        d = {f["key"]: f["detail"] for f in score(out_of_stock=1, low_stock=1, negative=1, stocked_items=1)["factors"]}
        self.assertEqual(d["availability"], "1 of 1 stocked item is out of stock.")
        self.assertEqual(d["low_stock"], "1 item is at or below the reorder level.")
        self.assertEqual(d["negative_stock"], "1 item has a negative balance in some warehouse.")
        d = {f["key"]: f["detail"] for f in score(out_of_stock=3, low_stock=2)["factors"]}
        self.assertEqual(d["availability"], "3 of 100 stocked items are out of stock.")

    def test_every_factor_explains_itself(self):
        for f in score(out_of_stock=3, low_stock=2)["factors"]:
            self.assertTrue(f["detail"])
            self.assertLessEqual(f["points"], f["weight"])


if __name__ == "__main__":
    unittest.main()
