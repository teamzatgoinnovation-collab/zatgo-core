"""Gym membership logic: renewal, billing, check-in. Business rules live here;
api/v1/gym/* is a thin layer. Billing goes through ERPNext's Sales Invoice."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent


def renew(membership: str) -> dict:
    """New membership starting the day after this one ends (or today if it
    already lapsed), on the same plan and trainer."""
    old = frappe.get_doc("ZG Gym Membership", membership)
    old.check_permission("read")
    frappe.has_permission("ZG Gym Membership", "create", throw=True)
    if old.status == "Cancelled":
        frappe.throw(_("A cancelled membership cannot be renewed"))
    if frappe.db.exists("ZG Gym Membership", {"renewed_from": old.name}):
        frappe.throw(_("Membership {0} was already renewed").format(old.name))
    start = max(add_days(getdate(old.end_date), 1), getdate())
    new = frappe.get_doc(
        {
            "doctype": "ZG Gym Membership",
            "member": old.member,
            "plan": old.plan,
            "company": old.company,
            "trainer": old.trainer,
            "start_date": start,
            "renewed_from": old.name,
        }
    ).insert()
    return new.as_dict()


def bill(membership: str) -> dict:
    """Sales Invoice for the membership; idempotent per membership."""
    m = frappe.get_doc("ZG Gym Membership", membership)
    m.check_permission("write")
    frappe.has_permission("Sales Invoice", "create", throw=True)
    client_id = f"gym-membership-{m.name}"
    existing = find_by_client_id("Sales Invoice", client_id)
    if existing or m.sales_invoice:
        name = existing or m.sales_invoice
        return {"sales_invoice": name, "created": False}
    item = frappe.db.get_value("ZG Gym Plan", m.plan, "item")
    if not item:
        frappe.throw(_("Plan {0} has no Billing Item").format(m.plan))
    si = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": m.member,
            "company": m.company,
            "posting_date": getdate(),
            "set_posting_time": 1,
            "due_date": getdate(),
            "zatgo_client_id": client_id,
            "items": [{"item_code": item, "qty": 1, "rate": m.amount}],
        }
    )
    si, created = insert_idempotent(si, doctype="Sales Invoice", client_id=client_id)
    frappe.db.set_value("ZG Gym Membership", m.name, "sales_invoice", si.name)
    return {"sales_invoice": si.name, "created": created}


def check_in(membership: str) -> dict:
    frappe.has_permission("ZG Gym Attendance", "create", throw=True)
    row = frappe.get_doc(
        {"doctype": "ZG Gym Attendance", "membership": membership, "check_in": now_datetime()}
    ).insert()
    return {"name": row.name, "check_in": get_datetime(row.check_in).isoformat()}
