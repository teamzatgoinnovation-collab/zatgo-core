"""When a scheduled task runs next. Pure python; datetimes are naive, in the site's timezone."""

from __future__ import annotations

from datetime import datetime, time, timedelta

FREQUENCIES = ("Hourly", "Daily", "Weekly", "Monthly")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MAX_DAY_OF_MONTH = 28  # every month has it, so "monthly" never skips February


def to_time(value) -> time:
	"""'08:30', '08:30:00', datetime.time, or Frappe's timedelta Time values."""
	if isinstance(value, time):
		return value
	if isinstance(value, timedelta):
		secs = int(value.total_seconds()) % 86400
		return time(secs // 3600, secs % 3600 // 60, secs % 60)
	parts = [int(p) for p in str(value or "08:00:00").split(":")[:3]]
	while len(parts) < 3:
		parts.append(0)
	return time(*parts)


def next_run_after(frequency: str, after: datetime, time_of_day="08:00:00", weekday="Monday", day_of_month=1) -> datetime:
	"""First run time strictly after `after`."""
	if frequency not in FREQUENCIES:
		raise ValueError(f"Unknown frequency '{frequency}'")
	if frequency == "Hourly":
		return after.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
	at = to_time(time_of_day)
	if frequency == "Daily":
		cand = datetime.combine(after.date(), at)
		return cand if cand > after else cand + timedelta(days=1)
	if frequency == "Weekly":
		if weekday not in WEEKDAYS:
			raise ValueError(f"Unknown weekday '{weekday}'")
		target = WEEKDAYS.index(weekday)
		day = after.date() + timedelta(days=(target - after.weekday()) % 7)
		cand = datetime.combine(day, at)
		return cand if cand > after else cand + timedelta(days=7)
	dom = max(1, min(int(day_of_month or 1), MAX_DAY_OF_MONTH))
	cand = datetime.combine(after.date().replace(day=dom), at)
	if cand > after:
		return cand
	year, month = (after.year + 1, 1) if after.month == 12 else (after.year, after.month + 1)
	return datetime.combine(after.date().replace(year=year, month=month, day=dom), at)
