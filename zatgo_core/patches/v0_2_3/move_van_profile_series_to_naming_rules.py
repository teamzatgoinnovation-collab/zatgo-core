"""Move per-driver series off ZG Van Sale Profile into ZG Sales Invoice Naming Settings.

The profile's sales_invoice_naming_series / sales_return_naming_series only
ever applied to invoices the VanSale API created; the desk ignored them. They
are now rules keyed on user + company and enforced for every Sales Invoice
(services/sales_invoice_naming.py). The fields are gone from the DocType JSON
but Frappe keeps the old columns, so they're read with SQL here.

Rows that can't become a valid rule (no company, series no longer a Sales
Invoice option, ...) are skipped and printed rather than failing the migrate;
nothing about existing invoices changes either way.
"""

from __future__ import annotations

import frappe
from frappe.model.naming import get_default_naming_series

from zatgo_core.services.naming_series import get_naming_series_options, resolve_series_for_return_state
from zatgo_core.services.sales_invoice_naming import SETTINGS_DOCTYPE, validate_rules


def execute() -> None:
    if not frappe.db.has_column("ZG Van Sale Profile", "sales_invoice_naming_series"):
        return
    profiles = frappe.db.sql(
        """
        select user, warehouse, sales_invoice_naming_series, sales_return_naming_series
        from `tabZG Van Sale Profile`
        where ifnull(sales_invoice_naming_series, '') != ''
           or ifnull(sales_return_naming_series, '') != ''
        """,
        as_dict=True,
    )
    if not profiles:
        return

    options = get_naming_series_options("Sales Invoice")
    default_series = get_default_naming_series("Sales Invoice")
    default_company = frappe.db.get_single_value("Global Defaults", "default_company")
    settings = frappe.get_single(SETTINGS_DOCTYPE)
    existing = {(r.user, r.company) for r in settings.rules}

    for p in profiles:
        company = (p.warehouse and frappe.db.get_value("Warehouse", p.warehouse, "company")) or default_company
        normal = (p.sales_invoice_naming_series or "").strip() or default_series
        ret = (p.sales_return_naming_series or "").strip() or (
            normal and resolve_series_for_return_state(normal, options, True)
        )
        if not (company and normal and ret) or (p.user, company) in existing:
            print(f"ZG Van Sale Profile {p.user}: series not migrated (company={company}, {normal} / {ret})")
            continue

        row = settings.append(
            "rules",
            {"user": p.user, "company": company, "normal_series": normal, "return_series": ret, "enabled": 1},
        )
        try:
            validate_rules(settings.rules)
        except frappe.ValidationError as e:
            settings.remove(row)
            print(f"ZG Van Sale Profile {p.user}: series not migrated ({e})")
            continue
        existing.add((p.user, company))

    settings.save(ignore_permissions=True)
