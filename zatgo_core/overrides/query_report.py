"""Run / export of query reports with the IFRS Report Template switch applied
(hooks.py override_whitelisted_methods; services/report_templates.py).

Thin wrappers: they only drop `report_template` from the filters of the financial statements when
the site has IFRS templates off, then call Frappe's own function unchanged."""

from __future__ import annotations

import inspect

import frappe
from frappe.desk import query_report as frappe_query_report

from zatgo_core.services.report_templates import classic_filters


# Frappe's own parameters, read once: the override forwards whatever Frappe's `run` accepts, so a
# parameter Frappe adds or drops later neither disappears here nor raises a TypeError on every report.
_UPSTREAM_PARAMS = frozenset(inspect.signature(frappe_query_report.run).parameters)


def forward_kwargs(kwargs: dict) -> dict:
    """[kwargs] limited to what Frappe's `run` takes (a `**kwargs` whitelisted function is handed the
    whole request, `cmd` and all)."""
    return {k: v for k, v in kwargs.items() if k in _UPSTREAM_PARAMS}


@frappe.whitelist()
@frappe.read_only()
def run(report_name: str, filters: str | dict | None = None, **kwargs) -> dict:
    kwargs = forward_kwargs(kwargs)
    kwargs.pop("report_name", None)
    return frappe_query_report.run(
        report_name=report_name, filters=classic_filters(report_name, filters), **kwargs
    )


@frappe.whitelist()
def export_query():
    form = frappe.local.form_dict
    if form.get("report_name") and form.get("filters"):
        form["filters"] = classic_filters(form["report_name"], form["filters"])
    return frappe_query_report.export_query()
