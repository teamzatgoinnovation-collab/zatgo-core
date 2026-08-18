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


def _parse_quotation_items(items: Any) -> list[dict[str, Any]]:
    """Same shape as _parse_items, plus an optional free-text description
    and billing-type label (e.g. "One-time", "Annually") — Quotation-only
    fields, so kept separate rather than growing the shared parser."""
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
        if raw.get("description"):
            row["description"] = raw["description"]
        if raw.get("billing_type"):
            row["zatgo_billing_type"] = raw["billing_type"]
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


def _cancel_doc(doctype: str, name: str, map_doc: Any) -> dict[str, Any]:
    require_login()
    require_str(name, "name")
    frappe.has_permission(doctype, "cancel", doc=name, throw=True)
    doc = frappe.get_doc(doctype, name)
    if int(doc.docstatus or 0) == 2:
        return ok(map_doc(doc), meta={"stub": False, "cancelled": False, "source": doctype})
    if int(doc.docstatus or 0) != 1:
        frappe.throw(f"{doctype} {name} must be submitted before it can be cancelled")
    doc.cancel()
    frappe.db.commit()
    return ok(map_doc(doc), meta={"stub": False, "cancelled": True, "source": doctype})


def _amend_doc(doctype: str, name: str, map_doc: Any) -> dict[str, Any]:
    """Correct a cancelled document by creating a new linked draft (amended_from),
    ERPNext's own audit-trail-preserving correction mechanism — never edit or
    resurrect the cancelled document itself."""
    require_login()
    require_str(name, "name")
    frappe.has_permission(doctype, "create", throw=True)
    original = frappe.get_doc(doctype, name)
    if int(original.docstatus or 0) != 2:
        frappe.throw(f"Only a cancelled {doctype} can be amended")
    new_doc = frappe.copy_doc(original)
    new_doc.amended_from = name
    new_doc.docstatus = 0
    # copy_doc carries over zatgo_client_id too, which collides with the original's
    # DB-level unique constraint — the amended doc is a new logical document.
    if hasattr(new_doc, "zatgo_client_id"):
        new_doc.zatgo_client_id = None
    new_doc.insert()
    frappe.db.commit()
    return ok(map_doc(new_doc), meta={"stub": False, "amended_from": name, "source": doctype})


def create_customer(
    customer_name: str,
    customer_type: str | None = None,
    customer_group: str | None = None,
    territory: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import enrich_customer_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Customer", cid)
        if existing:
            return ok(
                enrich_customer_doc(frappe.get_doc("Customer", existing)),
                meta={"stub": False, "idempotent": True, "source": "Customer"},
            )
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
            "zatgo_client_id": cid,
        }
    )
    if not doc.customer_group:
        doc.customer_group = frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups"
    if not doc.territory:
        doc.territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
    if cid:
        doc, created = insert_idempotent(doc, doctype="Customer", client_id=cid)
    else:
        doc.insert()
        created = True
    frappe.db.commit()

    return ok(
        enrich_customer_doc(doc),
        meta={"stub": False, "created": created, "idempotent": not created, "source": "Customer"},
    )


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
        "disabled": "disabled",
    }
    for key, field in mapping.items():
        if key in data and data[key] is not None:
            setattr(doc, field, data[key])
    doc.save()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import enrich_customer_doc

    return ok(enrich_customer_doc(doc), meta={"stub": False, "updated": True, "source": "Customer"})


def create_item(
    item_code: str,
    item_name: str | None = None,
    item_group: str | None = None,
    stock_uom: str | None = None,
    standard_rate: float | int | str | None = None,
    is_stock_item: int | str | bool | None = 1,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import get_item
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Item", cid)
        if existing:
            return get_item(existing)
    frappe.has_permission("Item", "create", throw=True)
    code = require_str(item_code, "item_code")
    doc = frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": code,
            "item_name": (item_name or code).strip() or code,
            "item_group": (item_group or "").strip() or "All Item Groups",
            "stock_uom": (stock_uom or "").strip() or "Nos",
            "standard_rate": flt(standard_rate or 0),
            "is_stock_item": 1 if str(is_stock_item) not in ("0", "false", "False", "") else 0,
            "zatgo_client_id": cid,
        }
    )
    if cid:
        doc, _created = insert_idempotent(doc, doctype="Item", client_id=cid)
    else:
        doc.insert()
    frappe.db.commit()

    return get_item(doc.name)


def _bool_field(value: Any) -> int:
    return 1 if str(value).lower() in ("1", "true", "yes") else 0


def update_item(name: str, values: Any = None) -> dict[str, Any]:
    require_login()
    require_str(name, "name")
    frappe.has_permission("Item", "write", doc=name, throw=True)
    data = parse_json_dict(values, "values")
    doc = frappe.get_doc("Item", name)
    mapping = {
        "item_name": "item_name",
        "item_group": "item_group",
        "stock_uom": "stock_uom",
        "standard_rate": "standard_rate",
        "is_stock_item": "is_stock_item",
        "disabled": "disabled",
        "description": "description",
        "brand": "brand",
        "has_batch_no": "has_batch_no",
        "has_serial_no": "has_serial_no",
        "is_sales_item": "is_sales_item",
        "is_purchase_item": "is_purchase_item",
        "weight_per_unit": "weight_per_unit",
        "weight_uom": "weight_uom",
    }
    bool_fields = {"is_stock_item", "disabled", "has_batch_no", "has_serial_no", "is_sales_item", "is_purchase_item"}
    for key, field in mapping.items():
        if key in data and data[key] is not None:
            value = data[key]
            if field in ("standard_rate", "weight_per_unit"):
                value = flt(value)
            elif field in bool_fields:
                value = _bool_field(value)
            setattr(doc, field, value)
    if "sales_uom" in data and data["sales_uom"] and frappe.db.has_column("Item", "sales_uom"):
        doc.sales_uom = data["sales_uom"]

    default_warehouse = (data.get("default_warehouse") or "").strip() if "default_warehouse" in data else None
    if default_warehouse and frappe.db.exists("Warehouse", default_warehouse):
        company = doc.item_defaults[0].company if doc.item_defaults else _default_company()
        if doc.item_defaults:
            doc.item_defaults[0].default_warehouse = default_warehouse
        else:
            doc.append("item_defaults", {"company": company, "default_warehouse": default_warehouse})

    if "reorder_level" in data:
        reorder = flt(data.get("reorder_level") or 0)
        reorder_qty = flt(data.get("reorder_qty") or reorder)
        warehouse = default_warehouse or (
            doc.item_defaults[0].default_warehouse if doc.item_defaults else None
        )
        if reorder > 0 and warehouse and frappe.db.exists("Warehouse", warehouse):
            doc.reorder_levels = []
            doc.append(
                "reorder_levels",
                {"warehouse": warehouse, "warehouse_reorder_level": reorder, "warehouse_reorder_qty": reorder_qty},
            )
        elif reorder <= 0:
            doc.reorder_levels = []

    if "tax_template" in data:
        tax_template = (data.get("tax_template") or "").strip()
        if tax_template and frappe.db.exists("Item Tax Template", tax_template):
            doc.taxes = []
            doc.append("taxes", {"item_tax_template": tax_template})
        else:
            doc.taxes = []

    doc.save()
    frappe.db.commit()
    from zatgo_core.services.erpnext_reads import get_item

    return get_item(doc.name)


def _map_warehouse_doc(doc: Any) -> dict[str, Any]:
    return {
        "id": doc.name,
        "name": doc.warehouse_name or doc.name,
        "company": doc.company,
        "parent_warehouse": getattr(doc, "parent_warehouse", None),
        "disabled": int(doc.disabled or 0),
    }


def create_warehouse(
    warehouse_name: str,
    company: str | None = None,
    parent_warehouse: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Warehouse", cid)
        if existing:
            return ok(
                _map_warehouse_doc(frappe.get_doc("Warehouse", existing)),
                meta={"stub": False, "idempotent": True, "source": "Warehouse"},
            )
    frappe.has_permission("Warehouse", "create", throw=True)
    label = require_str(warehouse_name, "warehouse_name")
    company_name = _default_company(company)
    doc = frappe.get_doc(
        {
            "doctype": "Warehouse",
            "warehouse_name": label,
            "company": company_name,
            "is_group": 0,
            "parent_warehouse": (parent_warehouse or "").strip() or None,
            "zatgo_client_id": cid,
        }
    )
    if cid:
        doc, created = insert_idempotent(doc, doctype="Warehouse", client_id=cid)
    else:
        doc.insert()
        created = True
    frappe.db.commit()
    return ok(
        _map_warehouse_doc(doc),
        meta={"stub": False, "created": created, "idempotent": not created, "source": "Warehouse"},
    )


def update_warehouse(name: str, values: Any = None) -> dict[str, Any]:
    require_login()
    require_str(name, "name")
    frappe.has_permission("Warehouse", "write", doc=name, throw=True)
    data = parse_json_dict(values, "values")
    doc = frappe.get_doc("Warehouse", name)
    mapping = {
        "warehouse_name": "warehouse_name",
        "company": "company",
        "parent_warehouse": "parent_warehouse",
        "disabled": "disabled",
    }
    for key, field in mapping.items():
        if key in data and data[key] is not None:
            value = data[key]
            if field == "disabled":
                value = 1 if str(value) not in ("0", "false", "False", "") else 0
            setattr(doc, field, value)
    doc.save()
    frappe.db.commit()
    return ok(
        {
            "id": doc.name,
            "name": doc.warehouse_name or doc.name,
            "company": doc.company,
            "parent_warehouse": getattr(doc, "parent_warehouse", None),
            "disabled": int(doc.disabled or 0),
        },
        meta={"stub": False, "updated": True, "source": "Warehouse"},
    )


def _map_item_group_doc(doc: Any) -> dict[str, Any]:
    return {
        "id": doc.name,
        "name": doc.item_group_name or doc.name,
        "parent_item_group": getattr(doc, "parent_item_group", None),
        "is_group": int(doc.is_group or 0),
    }


def _default_item_group_parent() -> str | None:
    if frappe.db.exists("Item Group", "All Item Groups"):
        return "All Item Groups"
    root = frappe.get_all("Item Group", filters={"is_group": 1}, pluck="name", limit=1)
    return root[0] if root else None


def create_item_group(
    item_group_name: str,
    parent_item_group: str | None = None,
    is_group: int | str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Item Group", "create", throw=True)
    label = require_str(item_group_name, "item_group_name")
    parent = (parent_item_group or "").strip() or _default_item_group_parent()
    doc = frappe.get_doc(
        {
            "doctype": "Item Group",
            "item_group_name": label,
            "parent_item_group": parent,
            "is_group": 1 if str(is_group) in ("1", "true", "True") else 0,
        }
    )
    doc.insert()
    frappe.db.commit()
    return ok(_map_item_group_doc(doc), meta={"stub": False, "created": True, "source": "Item Group"})


def _map_account_doc(doc: Any) -> dict[str, Any]:
    return {
        "id": doc.name,
        "name": doc.name,
        "account_name": doc.account_name or doc.name,
        "account_number": doc.account_number,
        "parent_account": doc.parent_account,
        "account_type": doc.account_type,
        "root_type": doc.root_type,
        "is_group": int(doc.is_group or 0),
        "disabled": int(doc.disabled or 0),
        "company": doc.company,
        "account_currency": doc.account_currency,
    }


def create_account(
    account_name: str,
    parent_account: str,
    account_type: str | None = None,
    is_group: int | str | None = None,
    account_number: str | None = None,
    account_currency: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    require_login()
    frappe.has_permission("Account", "create", throw=True)
    label = require_str(account_name, "account_name")
    parent = require_str(parent_account, "parent_account")
    if not frappe.db.exists("Account", parent):
        frappe.throw(f"Parent account {parent} not found")
    parent_doc = frappe.get_doc("Account", parent)
    if not parent_doc.is_group:
        frappe.throw(f"{parent} is not a group account and cannot have child accounts")
    doc = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": label,
            "parent_account": parent,
            "company": (company or "").strip() or parent_doc.company,
            "root_type": parent_doc.root_type,
            "report_type": parent_doc.report_type,
            "account_type": (account_type or "").strip() or None,
            "account_number": (account_number or "").strip() or None,
            "account_currency": (account_currency or "").strip() or None,
            "is_group": 1 if str(is_group) in ("1", "true", "True") else 0,
        }
    )
    doc.insert()
    frappe.db.commit()
    return ok(_map_account_doc(doc), meta={"stub": False, "created": True, "source": "Account"})


def update_account(name: str, values: Any = None) -> dict[str, Any]:
    require_login()
    require_str(name, "name")
    frappe.has_permission("Account", "write", doc=name, throw=True)
    data = parse_json_dict(values, "values")
    doc = frappe.get_doc("Account", name)
    mapping = {
        "account_name": "account_name",
        "account_type": "account_type",
        "account_number": "account_number",
        "disabled": "disabled",
    }
    for key, field in mapping.items():
        if key in data and data[key] is not None:
            value = data[key]
            if field == "disabled":
                value = 1 if str(value) not in ("0", "false", "False", "") else 0
            setattr(doc, field, value)
    doc.save()
    frappe.db.commit()
    return ok(_map_account_doc(doc), meta={"stub": False, "updated": True, "source": "Account"})


def create_supplier(
    supplier_name: str,
    supplier_type: str | None = None,
    supplier_group: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import get_supplier
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Supplier", cid)
        if existing:
            return get_supplier(existing)
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
            "zatgo_client_id": cid,
        }
    )
    if not doc.supplier_group:
        doc.supplier_group = (
            frappe.db.get_single_value("Buying Settings", "supplier_group") or "All Supplier Groups"
        )
    if cid:
        doc, _created = insert_idempotent(doc, doctype="Supplier", client_id=cid)
    else:
        doc.insert()
    frappe.db.commit()

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
        "disabled": "disabled",
    }
    for key, field in mapping.items():
        if key in data and data[key] is not None:
            value = data[key]
            if field == "disabled":
                value = 1 if str(value) not in ("0", "false", "False", "") else 0
            setattr(doc, field, value)
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
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_sales_invoice_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Sales Invoice", cid)
        if existing:
            return ok(
                map_sales_invoice_doc(frappe.get_doc("Sales Invoice", existing)),
                meta={"stub": False, "idempotent": True, "source": "Sales Invoice"},
            )
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
            "cost_center": (cost_center or "").strip() or None,
            "project": (project or "").strip() or None,
            "zatgo_client_id": cid,
        }
    )
    if cid:
        doc, created = insert_idempotent(doc, doctype="Sales Invoice", client_id=cid)
    else:
        doc.insert()
        created = True
    frappe.db.commit()

    return ok(
        map_sales_invoice_doc(doc),
        meta={"stub": False, "created": created, "idempotent": not created, "source": "Sales Invoice"},
    )


def create_quotation(
    customer: str,
    items: Any,
    company: str | None = None,
    transaction_date: str | None = None,
    valid_till: str | None = None,
    terms: str | None = None,
    cost_center: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_quotation_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Quotation", cid)
        if existing:
            return ok(
                map_quotation_doc(frappe.get_doc("Quotation", existing)),
                meta={"stub": False, "idempotent": True, "source": "Quotation"},
            )
    frappe.has_permission("Quotation", "create", throw=True)
    party = require_str(customer, "customer")
    if not frappe.db.exists("Customer", party):
        frappe.throw(f"Customer {party} not found")
    rows = _parse_quotation_items(items)
    doc = frappe.get_doc(
        {
            "doctype": "Quotation",
            "quotation_to": "Customer",
            "party_name": party,
            "company": _default_company(company),
            "transaction_date": getdate(transaction_date) if transaction_date else today(),
            "valid_till": getdate(valid_till) if valid_till else None,
            "terms": (terms or "").strip() or None,
            "items": rows,
            "cost_center": (cost_center or "").strip() or None,
            "zatgo_client_id": cid,
        }
    )
    if cid:
        doc, created = insert_idempotent(doc, doctype="Quotation", client_id=cid)
    else:
        doc.insert()
        created = True
    frappe.db.commit()

    return ok(
        map_quotation_doc(doc),
        meta={"stub": False, "created": created, "idempotent": not created, "source": "Quotation"},
    )


def submit_quotation(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_quotation_doc

    return _submit_doc("Quotation", name, map_quotation_doc)


def cancel_quotation(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_quotation_doc

    return _cancel_doc("Quotation", name, map_quotation_doc)


def create_sales_invoice_from_quotation(name: str) -> dict[str, Any]:
    """Convert a submitted (Ordered) Quotation into a Sales Invoice via
    ERPNext's own mapper — never re-derive item/tax mapping ourselves."""
    from erpnext.selling.doctype.quotation.quotation import make_sales_invoice

    from zatgo_core.services.erpnext_reads import map_sales_invoice_doc

    require_login()
    require_str(name, "name")
    if not frappe.db.exists("Quotation", name):
        frappe.throw(f"Quotation {name} not found")
    frappe.has_permission("Sales Invoice", "create", throw=True)
    source = frappe.get_doc("Quotation", name)
    if int(source.docstatus or 0) != 1:
        frappe.throw("Quotation must be submitted before converting to an invoice")
    invoice = make_sales_invoice(name)
    invoice.insert()
    frappe.db.commit()
    return ok(
        map_sales_invoice_doc(invoice),
        meta={"stub": False, "created": True, "source": "Sales Invoice", "from_quotation": name},
    )


def submit_sales_invoice(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_sales_invoice_doc
    from zatgo_core.services.zatca_qr import generate_and_store_zatca_qr

    require_login()
    require_str(name, "name")
    frappe.has_permission("Sales Invoice", "submit", doc=name, throw=True)
    doc = frappe.get_doc("Sales Invoice", name)
    if int(doc.docstatus or 0) == 2:
        frappe.throw(f"Sales Invoice {name} is cancelled")
    if int(doc.docstatus or 0) != 1:
        doc.submit()
        frappe.db.commit()
    try:
        generate_and_store_zatca_qr(doc)
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="ZATCA QR generation failed", message=frappe.get_traceback())
    return ok(map_sales_invoice_doc(doc), meta={"stub": False, "submitted": True, "source": "Sales Invoice"})


def cancel_sales_invoice(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_sales_invoice_doc

    return _cancel_doc("Sales Invoice", name, map_sales_invoice_doc)


def create_sales_return(
    return_against: str,
    items: Any,
    reason: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Partial/full Sales Return (credit note) against a submitted Sales Invoice."""
    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    from zatgo_core.services.erpnext_reads import map_sales_invoice_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Sales Invoice", cid)
        if existing:
            return ok(
                map_sales_invoice_doc(frappe.get_doc("Sales Invoice", existing)),
                meta={"stub": False, "idempotent": True, "source": "Sales Invoice"},
            )
    original_name = require_str(return_against, "return_against")
    if not frappe.db.exists("Sales Invoice", original_name):
        frappe.throw(f"Sales Invoice not found: {original_name}")
    original = frappe.get_doc("Sales Invoice", original_name)
    if int(original.docstatus or 0) != 1:
        frappe.throw(f"Sales Invoice {original_name} is not submitted.", frappe.ValidationError)
    if int(getattr(original, "is_return", 0) or 0):
        frappe.throw(f"Sales Invoice {original_name} is itself a return.", frappe.ValidationError)
    frappe.has_permission("Sales Invoice", "create", throw=True)

    if isinstance(items, str):
        import json

        items = json.loads(items)
    if not isinstance(items, list) or not items:
        frappe.throw("At least one line item is required")

    original_qty_by_item: dict[str, float] = {}
    for row in original.items or []:
        original_qty_by_item[row.item_code] = original_qty_by_item.get(row.item_code, 0) + flt(row.qty)

    requested_qty_by_item: dict[str, float] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        code = require_str(raw.get("item_code") or raw.get("item"), "item_code")
        qty = flt(raw.get("qty") or 0)
        if qty <= 0:
            frappe.throw("Return qty must be greater than zero")
        if code not in original_qty_by_item:
            frappe.throw(f"Item {code} was not sold on {original_name}")
        if qty > original_qty_by_item[code] + 1e-6:
            frappe.throw(
                f"Cannot return {qty} of {code} — only {original_qty_by_item[code]} was sold on {original_name}.",
                frappe.ValidationError,
            )
        requested_qty_by_item[code] = requested_qty_by_item.get(code, 0) + qty

    doc = make_return_doc("Sales Invoice", original_name)
    kept_items = []
    for row in doc.items or []:
        return_qty = requested_qty_by_item.get(row.item_code)
        if not return_qty:
            continue
        row.qty = -abs(return_qty)
        row.amount = row.qty * flt(row.rate)
        kept_items.append(row)
    if not kept_items:
        frappe.throw("None of the requested items match the original invoice")
    doc.items = kept_items
    if reason:
        doc.remarks = (f"{doc.remarks}\n" if doc.remarks else "") + f"Return reason: {reason}"
    # make_return_doc copies most fields from the original — the original's
    # own zatgo_client_id must not carry over onto the return (it would
    # collide with the unique constraint), so always overwrite it here.
    doc.zatgo_client_id = cid

    doc.run_method("calculate_taxes_and_totals")
    if cid:
        doc, created = insert_idempotent(doc, doctype="Sales Invoice", client_id=cid)
        if not created:
            return ok(
                map_sales_invoice_doc(doc),
                meta={"stub": False, "idempotent": True, "source": "Sales Invoice"},
            )
    else:
        doc.insert()
    try:
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.throw(
            "Could not create and submit Sales Return. Fix stock/accounts, then retry.",
            frappe.ValidationError,
        )
    doc.reload()
    return ok(map_sales_invoice_doc(doc), meta={"stub": False, "created": True, "source": "Sales Invoice"})


def create_purchase_invoice(
    supplier: str,
    items: Any,
    company: str | None = None,
    posting_date: str | None = None,
    due_date: str | None = None,
    remarks: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_purchase_invoice_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Purchase Invoice", cid)
        if existing:
            return ok(
                map_purchase_invoice_doc(frappe.get_doc("Purchase Invoice", existing)),
                meta={"stub": False, "idempotent": True, "source": "Purchase Invoice"},
            )
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
            "cost_center": (cost_center or "").strip() or None,
            "project": (project or "").strip() or None,
            "zatgo_client_id": cid,
        }
    )
    if cid:
        doc, created = insert_idempotent(doc, doctype="Purchase Invoice", client_id=cid)
    else:
        doc.insert()
        created = True
    frappe.db.commit()

    return ok(
        map_purchase_invoice_doc(doc),
        meta={"stub": False, "created": created, "idempotent": not created, "source": "Purchase Invoice"},
    )


def submit_purchase_invoice(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_purchase_invoice_doc

    return _submit_doc("Purchase Invoice", name, map_purchase_invoice_doc)


def cancel_purchase_invoice(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_purchase_invoice_doc

    return _cancel_doc("Purchase Invoice", name, map_purchase_invoice_doc)


def create_purchase_return(
    return_against: str,
    items: Any,
    reason: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Partial/full Purchase Return (debit note) against a submitted Purchase Invoice."""
    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    from zatgo_core.services.erpnext_reads import map_purchase_invoice_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Purchase Invoice", cid)
        if existing:
            return ok(
                map_purchase_invoice_doc(frappe.get_doc("Purchase Invoice", existing)),
                meta={"stub": False, "idempotent": True, "source": "Purchase Invoice"},
            )
    original_name = require_str(return_against, "return_against")
    if not frappe.db.exists("Purchase Invoice", original_name):
        frappe.throw(f"Purchase Invoice not found: {original_name}")
    original = frappe.get_doc("Purchase Invoice", original_name)
    if int(original.docstatus or 0) != 1:
        frappe.throw(f"Purchase Invoice {original_name} is not submitted.", frappe.ValidationError)
    if int(getattr(original, "is_return", 0) or 0):
        frappe.throw(f"Purchase Invoice {original_name} is itself a return.", frappe.ValidationError)
    frappe.has_permission("Purchase Invoice", "create", throw=True)

    if isinstance(items, str):
        import json

        items = json.loads(items)
    if not isinstance(items, list) or not items:
        frappe.throw("At least one line item is required")

    original_qty_by_item: dict[str, float] = {}
    for row in original.items or []:
        original_qty_by_item[row.item_code] = original_qty_by_item.get(row.item_code, 0) + flt(row.qty)

    requested_qty_by_item: dict[str, float] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        code = require_str(raw.get("item_code") or raw.get("item"), "item_code")
        qty = flt(raw.get("qty") or 0)
        if qty <= 0:
            frappe.throw("Return qty must be greater than zero")
        if code not in original_qty_by_item:
            frappe.throw(f"Item {code} was not bought on {original_name}")
        if qty > original_qty_by_item[code] + 1e-6:
            frappe.throw(
                f"Cannot return {qty} of {code} — only {original_qty_by_item[code]} was bought on {original_name}.",
                frappe.ValidationError,
            )
        requested_qty_by_item[code] = requested_qty_by_item.get(code, 0) + qty

    doc = make_return_doc("Purchase Invoice", original_name)
    kept_items = []
    for row in doc.items or []:
        return_qty = requested_qty_by_item.get(row.item_code)
        if not return_qty:
            continue
        row.qty = -abs(return_qty)
        row.amount = row.qty * flt(row.rate)
        kept_items.append(row)
    if not kept_items:
        frappe.throw("None of the requested items match the original bill")
    doc.items = kept_items
    if reason:
        doc.remarks = (f"{doc.remarks}\n" if doc.remarks else "") + f"Return reason: {reason}"
    doc.zatgo_client_id = cid

    doc.run_method("calculate_taxes_and_totals")
    if cid:
        doc, created = insert_idempotent(doc, doctype="Purchase Invoice", client_id=cid)
        if not created:
            return ok(
                map_purchase_invoice_doc(doc),
                meta={"stub": False, "idempotent": True, "source": "Purchase Invoice"},
            )
    else:
        doc.insert()
    try:
        doc.submit()
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.throw(
            "Could not create and submit Purchase Return. Fix stock/accounts, then retry.",
            frappe.ValidationError,
        )
    doc.reload()
    return ok(map_purchase_invoice_doc(doc), meta={"stub": False, "created": True, "source": "Purchase Invoice"})


def create_receive_payment(
    sales_invoice: str,
    amount: float | str | None = None,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Payment Entry", cid)
        if existing:
            return ok(
                map_payment_entry_doc(frappe.get_doc("Payment Entry", existing)),
                meta={"stub": False, "idempotent": True, "source": "Payment Entry"},
            )
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
    if cost_center:
        pe.cost_center = cost_center
    if project:
        pe.project = project
    pe.zatgo_client_id = cid
    if cid:
        pe, created = insert_idempotent(pe, doctype="Payment Entry", client_id=cid)
    else:
        pe.insert()
        created = True
    frappe.db.commit()

    return ok(
        map_payment_entry_doc(pe),
        meta={"stub": False, "created": created, "idempotent": not created, "source": "Payment Entry"},
    )


def create_pay_payment(
    purchase_invoice: str,
    amount: float | str | None = None,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Payment Entry", cid)
        if existing:
            return ok(
                map_payment_entry_doc(frappe.get_doc("Payment Entry", existing)),
                meta={"stub": False, "idempotent": True, "source": "Payment Entry"},
            )
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
    if cost_center:
        pe.cost_center = cost_center
    if project:
        pe.project = project
    pe.zatgo_client_id = cid
    if cid:
        pe, created = insert_idempotent(pe, doctype="Payment Entry", client_id=cid)
    else:
        pe.insert()
        created = True
    frappe.db.commit()

    return ok(
        map_payment_entry_doc(pe),
        meta={"stub": False, "created": created, "idempotent": not created, "source": "Payment Entry"},
    )


def _create_advance_payment(
    payment_type: str,
    party_type: str,
    party: str,
    amount: float | str,
    mode_of_payment: str | None,
    posting_date: str | None,
    reference_no: str | None,
    invoices: Any,
    client_id: str | None,
    company: str | None,
    cost_center: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """Build a Payment Entry directly from a party — not bound to a single invoice.
    Supports on-account/advance receipts (no invoices given) and allocating one
    payment across several outstanding invoices. ERPNext's own controller computes
    the unallocated remainder, account currency, and party/account defaults — this
    only assembles the doc and validates our own inputs before handing it off."""
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Payment Entry", cid)
        if existing:
            return ok(
                map_payment_entry_doc(frappe.get_doc("Payment Entry", existing)),
                meta={"stub": False, "idempotent": True, "source": "Payment Entry"},
            )
    frappe.has_permission("Payment Entry", "create", throw=True)

    party = require_str(party, "party")
    if not frappe.db.exists(party_type, party):
        frappe.throw(f"{party_type} {party} not found")
    amt = flt(amount)
    if amt <= 0:
        frappe.throw("Amount must be greater than zero")

    if isinstance(invoices, str):
        import json

        invoices = json.loads(invoices) if invoices.strip() else []
    invoices = invoices or []
    if not isinstance(invoices, list):
        frappe.throw("invoices must be a list")

    company_name = _default_company(company)
    date = getdate(posting_date) if posting_date else getdate(nowdate())

    from erpnext.accounts.doctype.payment_entry.payment_entry import (
        get_bank_cash_account,
        get_party_details,
        get_reference_details,
    )

    party_details = get_party_details(company_name, party_type, party, date)
    party_account = party_details["party_account"]
    # get_bank_cash_account returns a dict ({account, account_currency, account_type[, balance]}),
    # not a plain account name — extract the account itself.
    bank_account = (
        get_bank_cash_account(frappe._dict(company=company_name, mode_of_payment=mode_of_payment), None).get("account")
    )
    if not bank_account:
        frappe.throw("No default cash/bank account configured for this company")

    reference_doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
    party_field = "customer" if party_type == "Customer" else "supplier"

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = payment_type
    pe.company = company_name
    pe.posting_date = date
    pe.party_type = party_type
    pe.party = party
    if mode_of_payment:
        pe.mode_of_payment = mode_of_payment
    pe.reference_no = (reference_no or "").strip() or f"{payment_type}-{frappe.generate_hash(length=8)}"
    pe.reference_date = date
    pe.paid_amount = amt
    pe.received_amount = amt
    if cost_center:
        pe.cost_center = cost_center
    if project:
        pe.project = project
    if payment_type == "Receive":
        pe.paid_from = party_account
        pe.paid_to = bank_account
    else:
        pe.paid_from = bank_account
        pe.paid_to = party_account

    remaining = amt
    for raw in invoices:
        if not isinstance(raw, dict):
            frappe.throw("Each invoice allocation must be an object")
        inv_name = require_str(raw.get("name"), "invoices[].name")
        if not frappe.db.exists(reference_doctype, inv_name):
            frappe.throw(f"{reference_doctype} {inv_name} not found")
        inv_party, inv_docstatus, inv_outstanding = frappe.db.get_value(
            reference_doctype, inv_name, [party_field, "docstatus", "outstanding_amount"]
        )
        if inv_party != party:
            frappe.throw(f"{inv_name} does not belong to {party}")
        if int(inv_docstatus or 0) != 1:
            frappe.throw(f"{inv_name} must be submitted before allocating payment")
        outstanding = flt(inv_outstanding)
        if outstanding <= 0:
            frappe.throw(f"{inv_name} has no outstanding balance")
        requested = flt(raw.get("amount")) if raw.get("amount") is not None else outstanding
        alloc = min(requested, outstanding, remaining)
        if alloc <= 0:
            continue
        ref = get_reference_details(reference_doctype, inv_name, party_details["party_account_currency"])
        pe.append(
            "references",
            {
                "reference_doctype": reference_doctype,
                "reference_name": inv_name,
                "due_date": ref.get("due_date"),
                "total_amount": ref.get("total_amount"),
                "outstanding_amount": ref.get("outstanding_amount"),
                "allocated_amount": alloc,
            },
        )
        remaining -= alloc

    pe.zatgo_client_id = cid
    # set_missing_values() reads self.party_account as a transient attribute that
    # ERPNext's own client-side form normally seeds before save — since we build
    # this doc server-side, seed it ourselves with the value we already resolved.
    pe.party_account = party_account
    pe.set_missing_values()
    if cid:
        pe, created = insert_idempotent(pe, doctype="Payment Entry", client_id=cid)
    else:
        pe.insert()
        created = True
    frappe.db.commit()

    return ok(
        map_payment_entry_doc(pe),
        meta={
            "stub": False,
            "created": created,
            "idempotent": not created,
            "unallocated_amount": flt(pe.unallocated_amount),
            "source": "Payment Entry",
        },
    )


def create_receive_advance(
    party: str,
    amount: float | str,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    invoices: Any = None,
    company: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Receive from a Customer without requiring one bound Sales Invoice —
    supports on-account/advance receipts and allocating across several invoices."""
    return _create_advance_payment(
        "Receive",
        "Customer",
        party,
        amount,
        mode_of_payment,
        posting_date,
        reference_no,
        invoices,
        client_id,
        company,
        cost_center=cost_center,
        project=project,
    )


def create_pay_advance(
    party: str,
    amount: float | str,
    mode_of_payment: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    invoices: Any = None,
    company: str | None = None,
    cost_center: str | None = None,
    project: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Pay a Supplier without requiring one bound Purchase Invoice —
    supports on-account/advance payments and allocating across several bills."""
    return _create_advance_payment(
        "Pay",
        "Supplier",
        party,
        amount,
        mode_of_payment,
        posting_date,
        reference_no,
        invoices,
        client_id,
        company,
        cost_center=cost_center,
        project=project,
    )


def submit_payment_entry(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc

    return _submit_doc("Payment Entry", name, map_payment_entry_doc)


def cancel_payment_entry(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc

    return _cancel_doc("Payment Entry", name, map_payment_entry_doc)


_CASH_BANK_ACCOUNT_TYPES = {"Cash", "Bank"}


def _is_cash_or_bank_account(account: str) -> bool:
    return (frappe.get_cached_value("Account", account, "account_type") or "") in _CASH_BANK_ACCOUNT_TYPES


def _validate_voucher_type_accounts(voucher_type: str, rows: list[dict[str, Any]]) -> None:
    """Enforce standard double-entry voucher rules by account type, on top of
    ERPNext's own validation (which doesn't distinguish these):
      Contra    -> every line must be Cash/Bank
      Bank Entry (our Receipt/Payment split, see _create_split_entry) ->
                   the party line must NOT be Cash/Bank, every other line MUST be
      Journal Entry (plain) -> no line may be Cash/Bank — use Receipt, Payment,
                   or Contra instead so the cash/bank side is explicit
    Receipt/Payment against a single invoice or on-account go through Payment
    Entry (create_receive_payment/create_pay_payment/_create_advance_payment),
    which structurally enforces the same rule by construction — nothing to
    check here for those."""
    if voucher_type == "Contra Entry":
        for r in rows:
            if not _is_cash_or_bank_account(r["account"]):
                frappe.throw(
                    f"Contra entries can only use Cash or Bank accounts — {r['account']} is neither."
                )
    elif voucher_type == "Bank Entry":
        for r in rows:
            if r.get("party_type"):
                if _is_cash_or_bank_account(r["account"]):
                    frappe.throw(f"{r['account']} cannot be the party account and a Cash/Bank account at once.")
            elif not _is_cash_or_bank_account(r["account"]):
                frappe.throw(f"{r['account']} must be a Cash or Bank account for a split Receipt/Payment.")
    else:
        for r in rows:
            if _is_cash_or_bank_account(r["account"]):
                frappe.throw(
                    f"{r['account']} is a Cash/Bank account — use Receipt, Payment, or Contra instead of a "
                    "plain Journal Entry."
                )


def create_journal_entry(
    accounts: Any,
    company: str | None = None,
    posting_date: str | None = None,
    user_remark: str | None = None,
    voucher_type: str | None = None,
    reference_no: str | None = None,
    reference_date: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_journal_entry_doc
    from zatgo_core.services.idempotency import find_by_client_id, insert_idempotent

    require_login()
    cid = (client_id or "").strip() or None
    if cid:
        existing = find_by_client_id("Journal Entry", cid)
        if existing:
            return ok(
                map_journal_entry_doc(frappe.get_doc("Journal Entry", existing)),
                meta={"stub": False, "idempotent": True, "source": "Journal Entry"},
            )
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
        if not frappe.db.exists("Account", account):
            frappe.throw(f"Account {account} not found")
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
        if raw.get("cost_center"):
            row["cost_center"] = raw["cost_center"]
        if raw.get("user_remark"):
            row["user_remark"] = raw["user_remark"]
        rows.append(row)

    _validate_voucher_type_accounts((voucher_type or "Journal Entry").strip() or "Journal Entry", rows)

    if abs(total_debit - total_credit) > 0.005:
        frappe.throw(f"Journal is not balanced (debit {total_debit} vs credit {total_credit})")
    if not any(r["debit_in_account_currency"] > 0 for r in rows) or not any(
        r["credit_in_account_currency"] > 0 for r in rows
    ):
        frappe.throw("Voucher must have at least one Debit and one Credit entry")

    doc = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "voucher_type": (voucher_type or "Journal Entry").strip() or "Journal Entry",
            "company": _default_company(company),
            "posting_date": getdate(posting_date) if posting_date else today(),
            "user_remark": (user_remark or "").strip() or None,
            "cheque_no": (reference_no or "").strip() or None,
            "cheque_date": getdate(reference_date) if reference_date else None,
            "accounts": rows,
            "zatgo_client_id": cid,
        }
    )
    if cid:
        doc, created = insert_idempotent(doc, doctype="Journal Entry", client_id=cid)
    else:
        doc.insert()
        created = True
    frappe.db.commit()

    return ok(
        map_journal_entry_doc(doc),
        meta={"stub": False, "created": created, "idempotent": not created, "source": "Journal Entry"},
    )


def submit_journal_entry(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_journal_entry_doc

    return _submit_doc("Journal Entry", name, map_journal_entry_doc)


def _create_split_entry(
    party_type: str,
    party: str,
    lines: Any,
    posting_date: str | None,
    reference_no: str | None,
    remarks: str | None,
    cost_center: str | None,
    company: str | None,
    client_id: str | None,
) -> dict[str, Any]:
    """Multi-line receipt/payment: an auto-resolved party (receivable/payable)
    line plus a caller-supplied split across several cash/bank accounts — for
    a single transaction touching more than one account (e.g. part cash, part
    card). Built on the same Journal Entry primitive as Contra; delegates to
    create_journal_entry for balancing, validation, and idempotency rather
    than duplicating any of that."""
    require_login()
    party = require_str(party, "party")
    if not frappe.db.exists(party_type, party):
        frappe.throw(f"{party_type} {party} not found")

    if isinstance(lines, str):
        import json

        lines = json.loads(lines) if lines.strip() else []
    if not isinstance(lines, list) or len(lines) < 1:
        frappe.throw("At least one account line is required")

    company_name = _default_company(company)
    date = getdate(posting_date) if posting_date else getdate(nowdate())

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_details

    party_details = get_party_details(company_name, party_type, party, date)
    party_account = party_details["party_account"]

    is_receive = party_type == "Customer"
    total = 0.0
    accounts: list[dict[str, Any]] = []
    for raw in lines:
        if not isinstance(raw, dict):
            frappe.throw("Each account line must be an object")
        account = require_str(raw.get("account"), "lines[].account")
        amt = flt(raw.get("amount"))
        if amt <= 0:
            frappe.throw("Each line amount must be greater than zero")
        total += amt
        accounts.append(
            {
                "account": account,
                "debit": amt if is_receive else 0,
                "credit": 0 if is_receive else amt,
                "cost_center": raw.get("cost_center") or cost_center or None,
            }
        )
    accounts.append(
        {
            "account": party_account,
            "debit": 0 if is_receive else total,
            "credit": total if is_receive else 0,
            "party_type": party_type,
            "party": party,
            "cost_center": cost_center or None,
        }
    )

    # Bank Entry requires a reference no/date — auto-generate one if the caller
    # didn't supply it, same as the Contra Entry flow.
    ref_no = (reference_no or "").strip() or f"Split-{frappe.generate_hash(length=8)}"

    return create_journal_entry(
        accounts=accounts,
        company=company_name,
        posting_date=str(date),
        user_remark=remarks,
        voucher_type="Bank Entry",
        reference_no=ref_no,
        reference_date=str(date),
        client_id=client_id,
    )


def create_split_receive(
    party: str,
    lines: Any,
    posting_date: str | None = None,
    reference_no: str | None = None,
    remarks: str | None = None,
    cost_center: str | None = None,
    company: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Receive from a Customer split across several cash/bank accounts in one entry."""
    return _create_split_entry(
        "Customer", party, lines, posting_date, reference_no, remarks, cost_center, company, client_id
    )


def create_split_pay(
    party: str,
    lines: Any,
    posting_date: str | None = None,
    reference_no: str | None = None,
    remarks: str | None = None,
    cost_center: str | None = None,
    company: str | None = None,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Pay a Supplier split across several cash/bank accounts in one entry."""
    return _create_split_entry(
        "Supplier", party, lines, posting_date, reference_no, remarks, cost_center, company, client_id
    )


def cancel_journal_entry(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_journal_entry_doc

    return _cancel_doc("Journal Entry", name, map_journal_entry_doc)
