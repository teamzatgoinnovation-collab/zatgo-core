"""MyBis -- Reports: a catalog, paginated runs and server-side CSV / Excel / PDF exports of the same table."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.api.response import ok
from zatgo_core.api.v1.mybis import _common
from zatgo_core.api.validators import parse_json_dict, parse_pagination, require_login
from zatgo_core.services.mybis import cache, queries, reports, scope


@frappe.whitelist(methods=["GET", "POST"])
def catalog() -> dict[str, Any]:
    """Every report with the group it belongs to and whether the caller may run it."""
    require_login()
    return ok({"reports": reports.catalog(), "formats": list(reports.FORMATS), "max_rows": reports.MAX_ROWS})


def _table(report: str, company, preset, from_date, to_date, compare, filters, refresh) -> tuple[Any, dict[str, Any], scope.Scope]:
    require_login()
    defn = reports.get(report)
    f = parse_json_dict(filters, "filters")
    reports.clean_filters(defn, f)
    s = scope.resolve_scope(company, preset, from_date, to_date, compare)
    queries.guard(*defn.kinds)
    args = {"report": report, "filters": f}
    key_params = {**s.meta(), **args}
    table, meta = cache.cached("report", s.company, key_params, lambda: reports.run(defn, s, f), refresh=str(refresh).lower() in ("1", "true", "yes"))
    return table, meta, s


@frappe.whitelist(methods=["GET", "POST"])
def run(
    report: str,
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
    filters: Any = None,
    page: int | str = 1,
    page_size: int | str = 50,
    refresh: Any = 0,
) -> dict[str, Any]:
    """Run a report for the period: typed columns and one page of rows (`total_rows` says how many there are)."""
    table, meta, s = _table(report, company, preset, from_date, to_date, compare, filters, refresh)
    page_i, size_i, _start = parse_pagination(page, page_size)
    return ok(reports.page(table, page_i, size_i), meta={**s.meta(), **meta})


@frappe.whitelist(methods=["GET", "POST"])
def export(
    report: str,
    format: str = "csv",
    company: str | None = None,
    preset: str | None = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: Any = 1,
    filters: Any = None,
) -> dict[str, Any]:
    """The whole table as csv | xlsx | pdf, generated on the server and returned base64-encoded with its file name."""
    # An export is an explicit act: it is always computed fresh, never served from the five-minute screen cache.
    table, _meta, s = _table(report, company, preset, from_date, to_date, compare, filters, 1)
    frappe.logger("zatgo_core.mybis").info("report export report=%s format=%s rows=%s user=%s", report, format, len(table["rows"]), frappe.session.user)
    return ok(reports.export(table, format), meta=s.meta())
