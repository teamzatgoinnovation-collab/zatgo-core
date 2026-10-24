"""Shape of a dashboard figure and a few pure helpers (no database)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from zatgo_core.services.mybis import period as periods


def _clean(x: float) -> float:
    """Rounded to 2 places, and never -0.0 (a negated zero balance would print as "-0.00")."""
    return round(x, 2) or 0.0


def metric(current: float | None, previous: float | None, *, higher_is_better: bool = True, **extra: Any) -> dict[str, Any]:
    """{value, previous_value, change, growth_percent, higher_is_better, ...}. `previous` None = not compared;
    growth_percent is None when there is nothing to compare with (previous is 0 or missing) -- never a made-up 0 or 100."""
    out: dict[str, Any] = {
        "value": None if current is None else _clean(current),
        "previous_value": None if previous is None else _clean(previous),
        "change": None,
        "growth_percent": None,
        "higher_is_better": higher_is_better,
    }
    if current is not None and previous is not None:
        out["change"] = _clean(current - previous)
        out["growth_percent"] = periods.growth_percent(current, previous)
    out.update(extra)
    return out


def percent(part: float | None, whole: float | None) -> float | None:
    """part / whole in percent (2 places); None when whole is 0 / missing."""
    if part is None or not whole:
        return None
    return round(part / whole * 100, 2)


def auto_bucket(days: int) -> str:
    """Trend granularity for a range of `days`: day up to 62 days, week up to ~a year, else month."""
    if days <= 62:
        return "day"
    if days <= 400:
        return "week"
    return "month"


def bucket_start(d: date, bucket: str) -> date:
    if bucket == "day":
        return d
    if bucket == "week":
        return d - timedelta(days=d.weekday())
    if bucket == "month":
        return d.replace(day=1)
    raise ValueError(f"Unknown bucket: {bucket!r}")


def fill_series(rows: dict[date, float], start: date, end: date, bucket: str) -> list[dict[str, Any]]:
    """Continuous series from `start` to `end`: a bucket with no sales is an explicit 0, so a gap is never drawn as a line
    jumping over it. `rows` is keyed by bucket start date."""
    out: list[dict[str, Any]] = []
    cursor = bucket_start(start, bucket)
    while cursor <= end:
        out.append({"date": cursor.isoformat(), "value": round(rows.get(cursor, 0.0), 2)})
        if bucket == "day":
            cursor += timedelta(days=1)
        elif bucket == "week":
            cursor += timedelta(days=7)
        else:
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out
