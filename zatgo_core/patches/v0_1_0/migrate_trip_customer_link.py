"""Resolve free-text ZG Trip.customer values to Customer links after field change."""

from __future__ import annotations

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "ZG Trip"):
        return
    if not frappe.db.has_column("ZG Trip", "customer"):
        return

    rows = frappe.db.sql(
        "select name, customer from `tabZG Trip` where ifnull(customer, '') != ''",
        as_dict=True,
    )
    for row in rows:
        cust = (row.customer or "").strip()
        if not cust:
            continue
        if frappe.db.exists("Customer", cust):
            continue
        by_name = frappe.db.get_value("Customer", {"customer_name": cust}, "name")
        if by_name:
            frappe.db.set_value("ZG Trip", row.name, "customer", by_name, update_modified=False)
