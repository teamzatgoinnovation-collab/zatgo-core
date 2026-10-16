"""Deterministic table analysis for CSV/XLSX attachments.

The model asks for an operation; the numbers come from here, never from the model.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict

MAX_RESULT_ROWS = 50
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬\u2212", "0123456789.,-")  # U+2212 is the typographic minus
# A number with optional thousands grouping, optionally wrapped in a short currency / unit label:
# "1,234.50", "SAR 99", "$-5", "12%", "5 kg". Labels hold no digits, so dates ("15/01/2024"), phone
# numbers and codes ("INV-2024-001") are not numbers.
_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?|\.\d+"
# A dot belongs to a label ("ر.س", "S.R.") only when no digit follows it; otherwise ".5" would read as the label "." plus 5.
_LABEL = r"(?:[^\d\s+\-,().]|\.(?!\d)){1,10}"
_VALUE = re.compile(rf"^(?P<s1>[-+])?\s*(?:(?P<pre>{_LABEL})\s*)?(?P<s2>[-+])?\s*(?P<num>{_NUMBER})\s*(?P<suf>{_LABEL})?$")
FUNCS = ("sum", "mean", "min", "max", "median", "count", "count_distinct")
OPS = ("eq", "ne", "gt", "gte", "lt", "lte", "contains")


class TableError(ValueError):
	pass


def to_number(value) -> float | None:
	"""'1,234.50', '(12)', 'SAR 99', '٣٤٫٥' -> float; None if not numeric."""
	if isinstance(value, bool):
		return None
	if isinstance(value, (int, float)):
		return float(value)
	s = str(value).strip().translate(_ARABIC_DIGITS)
	neg = s.startswith("(") and s.endswith(")")
	if neg:
		s = s[1:-1].strip()
	m = _VALUE.match(s)
	if not m or (m["s1"] and m["s2"]):
		return None
	# A letter label glued to the number is an identifier ("SKU1001", "SKU-1001", "A1"), not a
	# currency: "SAR 99" needs the space. Symbols may touch ("$99") and units may follow ("5kg").
	if m["pre"] and any(ch.isalpha() for ch in m["pre"]):
		sign = m.start("s2") if m["s2"] else m.start("num")
		if m.end("pre") == sign:
			return None
	n = float((m["s1"] or m["s2"] or "") + m["num"].replace(",", ""))
	return -n if neg else n


def _col(columns: list[str], name: str) -> int:
	lowered = {c.lower(): i for i, c in enumerate(columns)}
	if name in columns:
		return columns.index(name)
	if str(name).lower() in lowered:
		return lowered[str(name).lower()]
	raise TableError(f"Unknown column '{name}'. Columns: {', '.join(columns)}")


def _passes(row, columns, flt) -> bool:
	idx = _col(columns, flt.get("column", ""))
	op = flt.get("op", "eq")
	if op not in OPS:
		raise TableError(f"Unknown filter op '{op}'")
	cell, want = row[idx], flt.get("value")
	if op == "contains":
		return str(want).lower() in str(cell).lower()
	a, b = to_number(cell), to_number(want)
	if op in ("gt", "gte", "lt", "lte"):
		if a is None or b is None:
			return False
		return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
	same = (a == b) if a is not None and b is not None else str(cell).strip().lower() == str(want).strip().lower()
	return same if op == "eq" else not same


def apply_filters(columns, rows, filters):
	if isinstance(filters, dict):  # one filter given without the list around it
		filters = [filters]
	filters = filters or []
	for f in filters:
		if not isinstance(f, dict):
			raise TableError("Each filter must be an object like {\"column\": ..., \"op\": ..., \"value\": ...}")
	for f in filters:
		rows = [r for r in rows if _passes(r, columns, f)]
	return rows


def describe(columns: list[str], rows: list[list]) -> dict:
	cols = []
	for i, name in enumerate(columns):
		vals = [r[i] for r in rows if str(r[i]).strip() != ""]
		nums = [n for n in (to_number(v) for v in vals) if n is not None]
		info = {"name": name, "non_empty": len(vals), "empty": len(rows) - len(vals)}
		if vals and len(nums) / len(vals) >= 0.9:
			info.update(type="number", min=min(nums), max=max(nums), sum=round(sum(nums), 6), mean=round(sum(nums) / len(nums), 6))
		else:
			info.update(type="text", distinct=len({str(v) for v in vals}), sample=[str(v) for v in vals[:3]])
		cols.append(info)
	return {"rows": len(rows), "columns": cols, "head": [dict(zip(columns, r)) for r in rows[:5]]}


def _reduce(func: str, values: list):
	if func == "count":
		return len(values)
	if func == "count_distinct":
		return len({str(v) for v in values})
	nums = [n for n in (to_number(v) for v in values) if n is not None]
	if not nums:
		return None
	return {
		"sum": lambda: round(sum(nums), 6),
		"mean": lambda: round(sum(nums) / len(nums), 6),
		"min": lambda: min(nums),
		"max": lambda: max(nums),
		"median": lambda: statistics.median(nums),
	}[func]()


def aggregate(columns, rows, *, column: str | None, func: str, group_by: str | None = None, filters=None, limit: int = 20) -> dict:
	if func not in FUNCS:
		raise TableError(f"Unknown function '{func}'. Use one of: {', '.join(FUNCS)}")
	rows = apply_filters(columns, rows, filters)
	ci = _col(columns, column) if column else None
	if func != "count" and ci is None:
		raise TableError(f"'{func}' needs a column")
	if not group_by:
		vals = [r[ci] for r in rows] if ci is not None else rows
		return {"function": func, "column": column, "rows_used": len(rows), "value": _reduce(func, vals)}
	gi = _col(columns, group_by)
	groups: dict[str, list] = defaultdict(list)
	for r in rows:
		groups[str(r[gi])].append(r[ci] if ci is not None else r)
	out = [{group_by: k, func: _reduce(func, v)} for k, v in groups.items()]
	out.sort(key=lambda d: (d[func] is None, -(d[func] or 0) if isinstance(d[func], (int, float)) else 0))
	limit = max(1, min(int(limit or 20), MAX_RESULT_ROWS))
	return {"function": func, "column": column, "group_by": group_by, "rows_used": len(rows), "groups": len(out), "results": out[:limit], "truncated": len(out) > limit}


def select_rows(columns, rows, *, filters=None, limit: int = 10) -> dict:
	rows = apply_filters(columns, rows, filters)
	limit = max(1, min(int(limit or 10), MAX_RESULT_ROWS))
	return {"matched": len(rows), "rows": [dict(zip(columns, r)) for r in rows[:limit]], "truncated": len(rows) > limit}
