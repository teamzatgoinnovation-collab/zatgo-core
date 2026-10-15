"""Deterministic table analysis for CSV/XLSX attachments.

The model asks for an operation; the numbers come from here, never from the model.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict

MAX_RESULT_ROWS = 50
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
_NUM = re.compile(r"^[-+]?\d+(\.\d+)?([eE][-+]?\d+)?$")
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
	if not s:
		return None
	neg = s.startswith("(") and s.endswith(")")
	s = re.sub(r"[^\d.,eE+\-]", "", s.strip("()")).replace(",", "")
	if not _NUM.match(s):
		return None
	n = float(s)
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
	for f in filters or []:
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
