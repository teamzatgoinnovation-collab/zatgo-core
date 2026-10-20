"""Run / export of query reports with the IFRS Report Template switch applied
(hooks.py override_whitelisted_methods; services/report_templates.py).

Thin wrappers: they only drop `report_template` from the filters of the financial statements when
the site has IFRS templates off, then call Frappe's own function unchanged."""

from __future__ import annotations

import frappe
from frappe.desk import query_report as frappe_query_report

from zatgo_core.services.report_templates import classic_filters


@frappe.whitelist()
@frappe.read_only()
def run(
    report_name: str,
    filters: str | dict | None = None,
    user: str | None = None,
    ignore_prepared_report: bool = False,
    custom_columns: str | list | None = None,
    is_tree: bool = False,
    parent_field: str | None = None,
    are_default_filters: bool = True,
    js_filters: str | list | None = None,
) -> dict:
    return frappe_query_report.run(
        report_name=report_name,
        filters=classic_filters(report_name, filters),
        user=user,
        ignore_prepared_report=ignore_prepared_report,
        custom_columns=custom_columns,
        is_tree=is_tree,
        parent_field=parent_field,
        are_default_filters=are_default_filters,
        js_filters=js_filters,
    )


@frappe.whitelist()
def export_query():
    form = frappe.local.form_dict
    if form.get("report_name") and form.get("filters"):
        form["filters"] = classic_filters(form["report_name"], form["filters"])
    return frappe_query_report.export_query()
