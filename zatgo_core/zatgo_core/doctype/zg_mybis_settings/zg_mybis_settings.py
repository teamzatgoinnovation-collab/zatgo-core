"""ZG MyBis Settings controller -- the defaults and the limits of the read-only MyBis app.

`policy()` is what `api/v1/mybis/context.py` hands to the app, which then lets each user choose only inside it. Every limit is
written so that "nothing stored" means "no restriction": a Check on a Single reads 0 until the form is saved, so the fields say
*hide* / *disable* and never *show* / *allow*. A site that never opened this form, or a database edited by hand, can therefore
only make the app less restricted -- never break it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from zatgo_core.services.mybis import period

DOCTYPE = "ZG MyBis Settings"

# The nine dashboard cards, keyed as `services/mybis/dashboard.kpis` returns them: one "hide_kpi_<key>" Check each.
KPI_KEYS = (
    "total_sales",
    "net_sales",
    "gross_profit",
    "net_profit",
    "purchases",
    "expenses",
    "receivables",
    "payables",
    "stock_value",
)
# Report export formats (`services/mybis/reports.FORMATS`): one "disable_export_<format>" Check each.
EXPORT_FORMATS = ("csv", "xlsx", "pdf")
# Alert severities, most severe first (`services/mybis/insights.SEVERITIES`).
SEVERITIES = ("critical", "high", "medium", "low")
MAX_REFRESH_MINUTES = 1440
DEFAULT_PRESET = "this_month"


def _flag(value: Any) -> bool:
    return cint(value) == 1


def sanitize(stored: Mapping[str, Any] | None) -> dict[str, Any]:
    """The limits for the app from the stored field values (strings from `tabSingles`, or nothing at all).

    Anything missing or malformed means "no restriction". All cards hidden falls back to all cards: an empty dashboard is not a
    policy, it is a mistake (the form refuses it; this guards a hand-edited database)."""
    raw = stored or {}
    minutes = min(max(cint(raw.get("min_refresh_minutes")), 0), MAX_REFRESH_MINUTES)
    severity = raw.get("min_alert_severity")
    kpis = [k for k in KPI_KEYS if not _flag(raw.get(f"hide_kpi_{k}"))]
    return {
        "min_refresh_minutes": minutes,
        "min_alert_severity": severity if severity in SEVERITIES else SEVERITIES[-1],
        "export_formats": [f for f in EXPORT_FORMATS if not _flag(raw.get(f"disable_export_{f}"))],
        "kpis": kpis or list(KPI_KEYS),
        "offline_copy": not _flag(raw.get("disable_offline_copy")),
    }


def stored() -> dict[str, Any]:
    """Every stored value of the Single, or {} where the table is not there yet (a site that has not migrated)."""
    try:
        return dict(frappe.db.get_singles_dict(DOCTYPE))
    except Exception:
        return {}


def policy() -> dict[str, Any]:
    return sanitize(stored())


def default_preset() -> str:
    preset = stored().get("default_preset")
    return preset if preset in period.PRESETS and preset != "custom" else DEFAULT_PRESET


class ZGMyBisSettings(Document):
    def validate(self) -> None:
        if not self.default_preset:
            self.default_preset = DEFAULT_PRESET
        elif self.default_preset not in period.PRESETS or self.default_preset == "custom":
            frappe.throw(_("{0} is not a period the dashboard can open on").format(self.default_preset))

        minutes = cint(self.min_refresh_minutes)
        if not 0 <= minutes <= MAX_REFRESH_MINUTES:
            frappe.throw(_("The shortest auto-refresh must be between 0 and {0} minutes").format(MAX_REFRESH_MINUTES))
        self.min_refresh_minutes = minutes

        if not self.min_alert_severity:
            self.min_alert_severity = SEVERITIES[-1]
        elif self.min_alert_severity not in SEVERITIES:
            frappe.throw(_("{0} is not an alert severity").format(self.min_alert_severity))

        if all(_flag(self.get(f"hide_kpi_{k}")) for k in KPI_KEYS):
            frappe.throw(_("Leave at least one dashboard card visible"))
