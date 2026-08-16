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


def submit_payment_entry(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc

    return _submit_doc("Payment Entry", name, map_payment_entry_doc)


def cancel_payment_entry(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_payment_entry_doc

    return _cancel_doc("Payment Entry", name, map_payment_entry_doc)


def create_journal_entry(
    accounts: Any,
    company: str | None = None,
    posting_date: str | None = None,
    user_remark: str | None = None,
    voucher_type: str | None = None,
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


def cancel_journal_entry(name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import map_journal_entry_doc

    return _cancel_doc("Journal Entry", name, map_journal_entry_doc)
