"""IFRS Report Templates on the financial statements, switched per site.

ERPNext's Balance Sheet / Profit and Loss Statement / Cash Flow run the classic account-tree report,
or -- when the `report_template` filter is set -- a Financial Report Template (e.g. "Standard Balance
Sheet (IFRS)"). That engine picks accounts by Account.account_category, so a site whose chart is not
categorised gets a different (and unbalanced) statement. ZG System Settings > "Enable IFRS Report
Templates" decides: off (default) = always the classic report, the filter is dropped here and hidden
in the Desk (public/js/ifrs_toggle.js); on = templates available as in ERPNext.
"""

from __future__ import annotations

import json

import frappe

SETTINGS = "ZG System Settings"
FIELD = "enable_ifrs_reports"
REPORTS = ("Balance Sheet", "Profit and Loss Statement", "Cash Flow")


def enabled() -> bool:
    try:
        return bool(frappe.db.get_single_value(SETTINGS, FIELD))
    except Exception:
        return False


def _loads(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def classic_filters(report_name: str, filters):
    """[filters] without `report_template` when this report must run classic; unchanged otherwise.
    Keeps the input's shape (JSON string in -> JSON string out)."""
    if report_name not in REPORTS or enabled():
        return filters
    parsed = _loads(filters)
    if not isinstance(parsed, dict) or not parsed.get("report_template"):
        return filters
    parsed = {k: v for k, v in parsed.items() if k != "report_template"}
    return json.dumps(parsed) if isinstance(filters, str) else parsed
