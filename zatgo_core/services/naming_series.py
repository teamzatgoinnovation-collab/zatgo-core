"""Naming-series helpers: pick the "-RET-" counterpart of a series.

ERPNext's naming_series Select field just lists a return-marked option
alongside the plain one -- nothing in core resolves between them based on
`is_return`. These helpers do that resolution generically, from whatever
options a doctype/site actually has configured, instead of assuming a
fixed prefix convention (sites differ: kasibasia's Sales Invoice options
are "SINV-"/"SINV-RET-", Purchase Invoice's are "ACC-PINV-.YYYY.-"/
"ACC-PINV-RET-.YYYY.-").
"""

from __future__ import annotations

import frappe


def get_naming_series_options(doctype: str) -> list[str]:
    meta = frappe.get_meta(doctype)
    field = meta.get_field("naming_series")
    if not field or not field.options:
        return []
    return [o.strip() for o in str(field.options).split("\n") if o.strip()]


def is_return_series(series: str) -> bool:
    return "RET-" in (series or "")


def strip_return_marker(series: str) -> str:
    return series.replace("RET-", "", 1)


def resolve_series_for_return_state(current: str, options: list[str], is_return: bool) -> str | None:
    """Return the series `current` should switch to given `is_return`.

    None means "already correct" or "no configured counterpart" -- callers
    should leave the document's naming_series untouched in either case.
    """
    if not current or is_return_series(current) == bool(is_return):
        return None

    if is_return:
        for opt in options:
            if opt != current and strip_return_marker(opt) == current:
                return opt
        return None

    stripped = strip_return_marker(current)
    return stripped if stripped != current and stripped in options else None


def counter_collision(prefix_a: str, prefix_b: str) -> bool:
    """True when two different series counters can emit the same name.

    A series emits `<counter prefix><zero-padded number>`. Equal prefixes share
    one tabSeries counter, so numbers never repeat. But if one prefix is the
    other plus only digits, two separate counters overlap: "S1-.##" at 101 and
    "S1-1.##" at 01 both produce "S1-101".
    """
    if not prefix_a or not prefix_b or prefix_a == prefix_b:
        return False
    short, long_ = sorted((prefix_a, prefix_b), key=len)
    return long_.startswith(short) and long_[len(short) :].isdigit()
