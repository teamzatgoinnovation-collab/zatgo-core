"""Date ranges for MyBis: presets, the comparison period and growth. Pure Python (no database), so it is unit-tested alone.

A preset's comparison period is the previous calendar unit of the same kind (this month -> last month); a custom range
is compared with the range of the same length right before it. Ranges are inclusive on both ends.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

PRESETS = (
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_quarter",
    "last_quarter",
    "this_year",
    "last_year",
    "custom",
)


@dataclass(frozen=True)
class Period:
    from_date: date
    to_date: date

    @property
    def days(self) -> int:
        return (self.to_date - self.from_date).days + 1

    def as_dict(self) -> dict[str, str]:
        return {"from": self.from_date.isoformat(), "to": self.to_date.isoformat()}


def _month_start(year: int, month: int) -> date:
    return date(year + (month - 1) // 12, (month - 1) % 12 + 1, 1)


def _month_range(year: int, month: int) -> Period:
    start = _month_start(year, month)
    return Period(start, date(start.year, start.month, calendar.monthrange(start.year, start.month)[1]))


def _quarter_range(year: int, quarter_index: int) -> Period:
    """quarter_index counts from 0 and may be negative / above 3 (it rolls the year)."""
    first = _month_start(year, quarter_index * 3 + 1)
    last = _month_range(first.year, first.month + 2)
    return Period(first, last.to_date)


def _week_range(day: date, week_start: int) -> Period:
    """The week containing `day`; week_start is a Python weekday (Monday=0 ... Sunday=6)."""
    start = day - timedelta(days=(day.weekday() - week_start) % 7)
    return Period(start, start + timedelta(days=6))


def resolve(
    preset: str,
    today: date,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    week_start: int = 0,
) -> Period:
    """The range for `preset` as of `today`. `custom` needs both dates (from <= to)."""
    if preset == "today":
        return Period(today, today)
    if preset == "yesterday":
        day = today - timedelta(days=1)
        return Period(day, day)
    if preset == "this_week":
        return _week_range(today, week_start)
    if preset == "last_week":
        return _week_range(today - timedelta(days=7), week_start)
    if preset == "this_month":
        return _month_range(today.year, today.month)
    if preset == "last_month":
        return _month_range(today.year, today.month - 1)
    if preset == "this_quarter":
        return _quarter_range(today.year, (today.month - 1) // 3)
    if preset == "last_quarter":
        return _quarter_range(today.year, (today.month - 1) // 3 - 1)
    if preset == "this_year":
        return Period(date(today.year, 1, 1), date(today.year, 12, 31))
    if preset == "last_year":
        return Period(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))
    if preset == "custom":
        if from_date is None or to_date is None:
            raise ValueError("A custom range needs both from_date and to_date")
        if from_date > to_date:
            raise ValueError("from_date is after to_date")
        return Period(from_date, to_date)
    raise ValueError(f"Unknown period preset: {preset!r}")


def previous(preset: str, current: Period, *, week_start: int = 0) -> Period:
    """The comparison period for `current` (resolved from `preset`)."""
    if preset in ("this_month", "last_month"):
        before = current.from_date - timedelta(days=1)
        return _month_range(before.year, before.month)
    if preset in ("this_quarter", "last_quarter"):
        before = current.from_date - timedelta(days=1)
        return _quarter_range(before.year, (before.month - 1) // 3)
    if preset in ("this_year", "last_year"):
        return Period(date(current.from_date.year - 1, 1, 1), date(current.from_date.year - 1, 12, 31))
    # day / week / custom: the same number of days right before.
    end = current.from_date - timedelta(days=1)
    return Period(end - timedelta(days=current.days - 1), end)


def growth_percent(current: float, previous_value: float) -> float | None:
    """Change in percent, rounded to 2 places; None when there is no base to compare with (previous is 0)."""
    if not previous_value:
        return None
    return round((current - previous_value) / abs(previous_value) * 100, 2)
