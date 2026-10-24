"""Inventory Health Score (0-100): a weighted, explained summary of the stock position. Pure arithmetic over counts and values the
caller measured from ERPNext (no database here), so the weights are visible and unit-tested.

Weights: availability 25, low stock 15, negative stock 15, dead stock 20, overstock 10, turnover 15.
"""

from __future__ import annotations

from typing import Any

WEIGHTS = {"availability": 25, "low_stock": 15, "negative_stock": 15, "dead_stock": 20, "overstock": 10, "turnover": 15}
TURNOVER_TARGET = 4.0  # stock turns a year that earns the full turnover points


def _ratio(part: float, whole: float) -> float:
    return 0.0 if not whole else min(1.0, max(0.0, part / whole))


def rating(score: int) -> str:
    return "good" if score >= 80 else ("fair" if score >= 60 else "poor")


def score(
    *,
    stocked_items: int,
    out_of_stock: int,
    low_stock: int,
    negative: int,
    stock_value: float,
    dead_value: float,
    overstock_value: float,
    turnover: float | None,
) -> dict[str, Any]:
    """`turnover` = annualised stock turns (None when nothing moved). Returns {score, rating, factors}; score is None when the
    company holds no stock records at all (a score of 100 for "nothing" would be false comfort)."""
    if stocked_items <= 0 and stock_value <= 0:
        return {"score": None, "rating": None, "factors": [], "note": "No stock records for this company."}

    def pts(key: str, lost: float) -> float:
        return round(WEIGHTS[key] * (1 - lost), 1)

    factors = [
        {
            "key": "availability",
            "label": "Stock availability",
            "weight": WEIGHTS["availability"],
            "points": pts("availability", _ratio(out_of_stock, stocked_items)),
            "detail": f"{out_of_stock} of {stocked_items} stocked items are out of stock.",
        },
        {
            "key": "low_stock",
            "label": "Low stock",
            "weight": WEIGHTS["low_stock"],
            "points": pts("low_stock", _ratio(low_stock, stocked_items)),
            "detail": f"{low_stock} items are at or below their reorder level.",
        },
        {
            "key": "negative_stock",
            "label": "Negative stock",
            "weight": WEIGHTS["negative_stock"],
            # a negative balance is a data-integrity problem, so each one weighs 5x an out-of-stock item
            "points": pts("negative_stock", _ratio(negative * 5, stocked_items)),
            "detail": f"{negative} items have a negative balance in some warehouse.",
        },
        {
            "key": "dead_stock",
            "label": "Dead stock",
            "weight": WEIGHTS["dead_stock"],
            "points": pts("dead_stock", _ratio(dead_value, stock_value)),
            "detail": f"{round(100 * _ratio(dead_value, stock_value))}% of stock value has had no outward movement for 90+ days.",
        },
        {
            "key": "overstock",
            "label": "Overstock",
            "weight": WEIGHTS["overstock"],
            "points": pts("overstock", _ratio(overstock_value, stock_value)),
            "detail": f"{round(100 * _ratio(overstock_value, stock_value))}% of stock value covers more than 180 days of sales.",
        },
        {
            "key": "turnover",
            "label": "Stock turnover",
            "weight": WEIGHTS["turnover"],
            "points": pts("turnover", 1 - min(1.0, (turnover or 0.0) / TURNOVER_TARGET)),
            "detail": "No stock was sold out in the last 90 days." if not turnover else f"Stock turns {turnover:.1f} times a year (target {TURNOVER_TARGET:.0f}+).",
        },
    ]
    total = int(round(sum(f["points"] for f in factors)))
    return {"score": total, "rating": rating(total), "factors": factors}
