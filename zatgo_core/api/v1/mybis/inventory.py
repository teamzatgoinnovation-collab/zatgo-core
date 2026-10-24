"""MyBis -- Inventory screen: stock position, health score and the lists behind each alert."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate, today

from zatgo_core.api.response import paginated
from zatgo_core.api.v1.mybis import _common
from zatgo_core.api.validators import parse_pagination, require_login
from zatgo_core.services.mybis import inventory, queries, scope


@frappe.whitelist(methods=["GET", "POST"])
def summary(company: str | None = None, refresh: Any = 0) -> dict[str, Any]:
    """Stock value / quantity today (a balance, so no period), alert counts, idle-days aging, turnover and the explained health score."""
    args = {"company": company, "preset": "today", "compare": 0}
    return _common.run("inventory_summary", args, ("stock", "items", "bin"), lambda s: {"currency": s.currency, **inventory.summary(s.company, getdate(today()))}, refresh)


@frappe.whitelist(methods=["GET", "POST"])
def alerts(
    kind: str = "low_stock",
    company: str | None = None,
    page: int | str = 1,
    page_size: int | str = 20,
) -> dict[str, Any]:
    """low_stock | out_of_stock | negative | slow_moving | overstock | fast_moving -- the rows behind an inventory alert."""
    require_login()
    s = scope.resolve_scope(company, "today", None, None, 0)
    queries.guard("stock", "items", "bin")
    page_i, size_i, _start = parse_pagination(page, page_size)
    rows, total = inventory.alerts(s.company, getdate(today()), kind, page_i, size_i)
    out = paginated(rows, page=page_i, page_size=size_i, total=total, sort=kind)
    out["meta"].update({"company": s.company, "currency": s.currency, "kind": kind})
    return out
