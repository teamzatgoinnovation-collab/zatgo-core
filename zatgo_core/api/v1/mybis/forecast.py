"""MyBis -- Forecast screen: statistical projections, always labelled as forecasts, with method, range, confidence and limitations."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import getdate, today

from zatgo_core.api.v1.mybis import _common
from zatgo_core.api.validators import require_login
from zatgo_core.services.mybis import forecast as fc
from zatgo_core.services.mybis import forecasting


@frappe.whitelist(methods=["GET", "POST"])
def project(
    subject: str = "sales",
    horizon: str = "30d",
    method: str = "auto",
    party: str | None = None,
    company: str | None = None,
    refresh: Any = 0,
) -> dict[str, Any]:
    """Forecast of `subject` (sales | revenue | purchases | cash_flow | customer + party) for `horizon` (7d | 30d | 90d | 12m)
    with `method` (auto | moving_average | weighted_moving_average | exponential_smoothing | holt)."""
    kind = forecasting.guard_kind(subject)
    args = {"company": company, "preset": "today", "compare": 0, "subject": subject, "horizon": horizon, "method": method, "party": party}
    return _common.run(
        "forecast",
        args,
        (kind,),
        lambda s: forecasting.build(s.company, s.currency, subject, horizon, method, party, getdate(today())),
        refresh,
        ttl=600,
    )


@frappe.whitelist(methods=["GET", "POST"])
def demand(horizon_days: int | str = 30, limit: int | str = 20, company: str | None = None, refresh: Any = 0) -> dict[str, Any]:
    """Inventory demand per stock item: forecast sales volume, stock, on order and the suggested reorder quantity (informational)."""
    args = {"company": company, "preset": "today", "compare": 0, "horizon_days": horizon_days, "limit": limit}
    return _common.run(
        "forecast_demand",
        args,
        ("sales", "bin"),
        lambda s: {"currency": s.currency, **forecasting.demand(s.company, int(horizon_days), int(limit), getdate(today()))},
        refresh,
        ttl=600,
    )


@frappe.whitelist(methods=["GET", "POST"])
def methods() -> dict[str, Any]:
    """The available forecast methods and horizons (the app builds its pickers from this)."""
    from zatgo_core.api.response import ok

    require_login()
    return ok({"methods": list(fc.METHODS), "horizons": list(forecasting.HORIZONS), "subjects": list(forecasting.SUBJECTS)})
