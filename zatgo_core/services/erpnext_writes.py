"""Create / update / submit helpers for ERPNext accounting DocTypes."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, getdate, nowdate, today

from zatgo_core.api.response import ok
from zatgo_core.api.validators import parse_json_dict, require_login, require_str


def _default_company(company: str | None = None) -> str:
    if company and str(company).strip():
        return str(company).strip()
    value = frappe.defaults.get_user_default("Company")
    if value:
        return value
    value = frappe.db.get_single_value("Global Defaults", "default_company")
    if value:
        return value
    companies = frappe.get_all("Company", pluck="name", limit=1)
    if companies:
        return companies[0]
    frappe.throw("No company configured")


def _parse_items(items: Any) -> list[dict[str, Any]]:
    if items is None:
        return []
    if isinstance(items, str):
        import json

        items = json.loads(items)
    if not isinstance(items, list) or not items:
        frappe.throw("At least one line item is required")
    rows: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            frappe.throw("Each item must be an object")
        item_code = require_str(raw.get("item_code") or raw.get("item"), "item_code")
        qty = flt(raw.get("qty") or 1)
        rate = flt(raw.get("rate") or 0)
        if qty <= 0:
            frappe.throw("Item qty must be greater than zero")
        row: dict[str, Any] = {"item_code": item_code, "qty": qty, "rate": rate}
        if raw.get("item_name"):
            row["item_name"] = raw["item_name"]
        if raw.get("uom"):
            row["uom"] = raw["uom"]
        rows.append(row)
    return rows


def _submit_doc(doctype: str, name: str, map_doc: Any) -> dict[str, Any]:
    require_login()
    require_str(name, "name")
    frappe.has_permission(doctype, "submit", doc=name, throw=True)
    doc = frappe.get_doc(doctype, name)
    if int(doc.docstatus or 0) == 1:
        return ok(map_doc(doc), meta={"stub": False, "submitted": False, "source": doctype})
    if int(doc.docstatus or 0) == 2:
        frappe.throw(f"{doctype} {name} is cancelled")
    doc.submit()
    frappe.db.commit()
    return ok(map_doc(doc), meta={"stub": False, "submitted": True, "source": doctype})


def create_customer(
    customer_name: str,
    customer_type: str | None = None,
    customer_group: str | None = None,
    territory: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Customer", "create", throw=True)
    name = require_str(customer_name, "customer_name")
    doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": (customer_type or "Company").strip() or "Company",
            "customer_group": (customer_group or "").strip() or None,
            "territory": (territory or "").strip() or None,
            "email_id": (email or "").strip() or None,
            "mobile_no": (phone or "").strip() or None,
        }
    )
    if not doc.customer_group:
        doc.customer_group = frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups"
    if not doc.territory:
        doc.territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
    doc.insert()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import enrich_customer_doc

    return ok(enrich_customer_doc(doc), meta={"stub": False, "created": True, "source": "Customer"})


def update_customer(name: str, values: Any = None) -> dict[str, Any]:
    require_login()
    require_str(name, "name")
    frappe.has_permission("Customer", "write", doc=name, throw=True)
    data = parse_json_dict(values, "values")
    doc = frappe.get_doc("Customer", name)
    mapping = {
        "customer_name": "customer_name",
        "customer_type": "customer_type",
        "customer_group": "customer_group",
        "territory": "territory",
        "email": "email_id",
        "phone": "mobile_no",
        "email_id": "email_id",
        "mobile_no": "mobile_no",
    }
    for key, field in mapping.items():
        if key in data and data[key] is not None:
            setattr(doc, field, data[key])
    doc.save()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import enrich_customer_doc

    return ok(enrich_customer_doc(doc), meta={"stub": False, "updated": True, "source": "Customer"})


def create_supplier(
    supplier_name: str,
    supplier_type: str | None = None,
    supplier_group: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Supplier", "create", throw=True)
    name = require_str(supplier_name, "supplier_name")
    doc = frappe.get_doc(
        {
            "doctype": "Supplier",
            "supplier_name": name,
            "supplier_type": (supplier_type or "Company").strip() or "Company",
            "supplier_group": (supplier_group or "").strip() or None,
            "email_id": (email or "").strip() or None,
            "mobile_no": (phone or "").strip() or None,
        }
    )
    if not doc.supplier_group:
        doc.supplier_group = (
            frappe.db.get_single_value("Buying Settings", "supplier_group") or "All Supplier Groups"
        )
    doc.insert()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import get_supplier

    return get_supplier(doc.name)


def update_supplier(name: str, values: Any = None) -> dict[str, Any]:
    require_login()
    require_str(name, "name")
    frappe.has_permission("Supplier", "write", doc=name, throw=True)
    data = parse_json_dict(values, "values")
    doc = frappe.get_doc("Supplier", name)
    mapping = {
        "supplier_name": "supplier_name",
        "supplier_type": "supplier_type",
        "supplier_group": "supplier_group",
        "email": "email_id",
        "phone": "mobile_no",
        "email_id": "email_id",
        "mobile_no": "mobile_no",
    }
    for key, field in mapping.items():
        if key in data and data[key] is not None:
            setattr(doc, field, data[key])
    doc.save()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import get_supplier

    return get_supplier(doc.name)


def create_sales_invoice(
    customer: str,
    items: Any,
    company: str | None = None,
    posting_date: str | None = None,
    due_date: str | None = None,
    remarks: str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Sales Invoice", "create", throw=True)
    party = require_str(customer, "customer")
    rows = _parse_items(items)
    doc = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": party,
            "company": _default_company(company),
            "posting_date": getdate(posting_date) if posting_date else today(),
            "due_date": getdate(due_date) if due_date else None,
            "remarks": (remarks or "").strip() or None,
            "items": rows,
        }
    )
    doc.insert()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import map_sales_invoice_doc

    return ok(map_sales_invoice_doc(doc), meta={"stub": False, "created": True, "source": "Sales Invoice"})


def submit_sales_invoice(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_sales_invoice_doc

    return _submit_doc("Sales Invoice", name, map_sales_invoice_doc)


def create_purchase_invoice(
    supplier: str,
    items: Any,
    company: str | None = None,
    posting_date: str | None = None,
    due_date: str | None = None,
    remarks: str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Purchase Invoice", "create", throw=True)
    party = require_str(supplier, "supplier")
    rows = _parse_items(items)
    doc = frappe.get_doc(
        {
            "doctype": "Purchase Invoice",
            "supplier": party,
            "company": _default_company(company),
            "posting_date": getdate(posting_date) if posting_date else today(),
            "due_date": getdate(due_date) if due_date else None,
            "remarks": (remarks or "").strip() or None,
            "items": rows,
        }
    )
    doc.insert()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import map_purchase_invoice_doc

    return ok(map_purchase_invoice_doc(doc), meta={"stub": False, "created": True, "source": "Purchase Invoice"})


def submit_purchase_invoice(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_purchase_invoice_doc

    return _submit_doc("Purchase Invoice", name, map_purchase_invoice_doc)


def create_receive_payment(
    sales_invoice: str,
    amount: float | str | None = None,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Payment Entry", "create", throw=True)
    si_name = require_str(sales_invoice, "sales_invoice")
    if not frappe.db.exists("Sales Invoice", si_name):
        frappe.throw(f"Sales Invoice {si_name} not found")
    si = frappe.get_doc("Sales Invoice", si_name)
    if int(si.docstatus or 0) != 1:
        frappe.throw("Sales Invoice must be submitted before receiving payment")
    paid = flt(amount) if amount is not None else flt(si.outstanding_amount)
    if paid <= 0:
        frappe.throw("Payment amount must be greater than zero")

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    pe = get_payment_entry("Sales Invoice", si_name, party_amount=paid)
    pe.posting_date = getdate(posting_date) if posting_date else getdate(nowdate())
    if mode_of_payment:
        pe.mode_of_payment = mode_of_payment
    if reference_no:
        pe.reference_no = reference_no
        pe.reference_date = pe.posting_date
    pe.insert()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc

    return ok(map_payment_entry_doc(pe), meta={"stub": False, "created": True, "source": "Payment Entry"})


def create_pay_payment(
    purchase_invoice: str,
    amount: float | str | None = None,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Payment Entry", "create", throw=True)
    pi_name = require_str(purchase_invoice, "purchase_invoice")
    if not frappe.db.exists("Purchase Invoice", pi_name):
        frappe.throw(f"Purchase Invoice {pi_name} not found")
    pi = frappe.get_doc("Purchase Invoice", pi_name)
    if int(pi.docstatus or 0) != 1:
        frappe.throw("Purchase Invoice must be submitted before paying")
    paid = flt(amount) if amount is not None else flt(pi.outstanding_amount)
    if paid <= 0:
        frappe.throw("Payment amount must be greater than zero")

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    pe = get_payment_entry("Purchase Invoice", pi_name, party_amount=paid)
    pe.posting_date = getdate(posting_date) if posting_date else getdate(nowdate())
    if mode_of_payment:
        pe.mode_of_payment = mode_of_payment
    if reference_no:
        pe.reference_no = reference_no
        pe.reference_date = pe.posting_date
    pe.insert()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc

    return ok(map_payment_entry_doc(pe), meta={"stub": False, "created": True, "source": "Payment Entry"})


def submit_payment_entry(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc

    return _submit_doc("Payment Entry", name, map_payment_entry_doc)


def create_journal_entry(
    accounts: Any,
    company: str | None = None,
    posting_date: str | None = None,
    user_remark: str | None = None,
    voucher_type: str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Journal Entry", "create", throw=True)
    if isinstance(accounts, str):
        import json

        accounts = json.loads(accounts)
    if not isinstance(accounts, list) or len(accounts) < 2:
        frappe.throw("Journal Entry needs at least two account lines")

    rows: list[dict[str, Any]] = []
    total_debit = 0.0
    total_credit = 0.0
    for raw in accounts:
        if not isinstance(raw, dict):
            frappe.throw("Each account line must be an object")
        account = require_str(raw.get("account"), "account")
        debit = flt(raw.get("debit") or 0)
        credit = flt(raw.get("credit") or 0)
        if debit < 0 or credit < 0:
            frappe.throw("Debit and credit must be non-negative")
        if debit and credit:
            frappe.throw("A line cannot have both debit and credit")
        if not debit and not credit:
            frappe.throw("Each line needs a debit or credit amount")
        total_debit += debit
        total_credit += credit
        row: dict[str, Any] = {
            "account": account,
            "debit_in_account_currency": debit,
            "credit_in_account_currency": credit,
        }
        if raw.get("party_type"):
            row["party_type"] = raw["party_type"]
        if raw.get("party"):
            row["party"] = raw["party"]
        if raw.get("user_remark"):
            row["user_remark"] = raw["user_remark"]
        rows.append(row)

    if abs(total_debit - total_credit) > 0.005:
        frappe.throw(f"Journal is not balanced (debit {total_debit} vs credit {total_credit})")

    doc = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "voucher_type": (voucher_type or "Journal Entry").strip() or "Journal Entry",
            "company": _default_company(company),
            "posting_date": getdate(posting_date) if posting_date else today(),
            "user_remark": (user_remark or "").strip() or None,
            "accounts": rows,
        }
    )
    doc.insert()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import map_journal_entry_doc

    return ok(map_journal_entry_doc(doc), meta={"stub": False, "created": True, "source": "Journal Entry"})


def submit_journal_entry(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_journal_entry_doc

    return _submit_doc("Journal Entry", name, map_journal_entry_doc)
