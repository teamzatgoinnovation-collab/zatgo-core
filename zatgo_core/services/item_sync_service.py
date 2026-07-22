"""Offline-first Item sync for ERPNext v16 (VanSale products)."""

from __future__ import annotations

import base64
from typing import Any

import frappe
from frappe.utils import cstr, flt

from zatgo_core.api.response import ok
from zatgo_core.api.validators import parse_json_dict, require_login, require_str
from zatgo_core.services.erpnext_writes import _default_company


def _as_dict(value: Any, field: str) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    return parse_json_dict(value, field)


def _find_by_client_id(client_id: str) -> str | None:
    if not client_id or not frappe.db.has_column("Item", "zatgo_client_id"):
        return None
    return frappe.db.get_value("Item", {"zatgo_client_id": client_id}, "name")


def _default_item_group() -> str:
    return frappe.db.get_single_value("Stock Settings", "item_group") or "Products"


def _default_uom() -> str:
    return frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos"


def _default_price_list() -> str | None:
    return frappe.db.get_single_value("Selling Settings", "selling_price_list")


def get_item_defaults() -> dict[str, Any]:
    """Defaults + pick lists for product forms."""
    require_login()
    company = _default_company()
    return ok(
        {
            "item_group": _default_item_group(),
            "stock_uom": _default_uom(),
            "sales_uom": _default_uom(),
            "is_stock_item": 1,
            "disabled": 0,
            "company": company,
            "default_price_list": _default_price_list(),
            "opening_warehouse": frappe.defaults.get_user_default("Warehouse"),
            "item_groups": frappe.get_all(
                "Item Group", filters={"is_group": 0}, pluck="name", order_by="name asc", limit=200
            )
            or frappe.get_all("Item Group", pluck="name", order_by="name asc", limit=200),
            "uoms": frappe.get_all("UOM", pluck="name", order_by="name asc", limit=300),
            "brands": frappe.get_all("Brand", pluck="name", order_by="name asc", limit=200)
            if frappe.db.exists("DocType", "Brand")
            else [],
            "price_lists": frappe.get_all(
                "Price List", filters={"selling": 1, "enabled": 1}, pluck="name", order_by="name asc", limit=100
            ),
            "warehouses": frappe.get_all(
                "Warehouse",
                filters={"is_group": 0, "company": company, "disabled": 0},
                pluck="name",
                order_by="name asc",
                limit=200,
            ),
            "item_tax_templates": frappe.get_all(
                "Item Tax Template", filters={"company": company}, pluck="name", order_by="name asc", limit=100
            )
            if frappe.db.exists("DocType", "Item Tax Template")
            else [],
            "income_accounts": frappe.get_all(
                "Account",
                filters={
                    "company": company,
                    "account_type": "Income Account",
                    "is_group": 0,
                    "disabled": 0,
                },
                pluck="name",
                order_by="name asc",
                limit=100,
            ),
            "expense_accounts": frappe.get_all(
                "Account",
                filters={
                    "company": company,
                    "root_type": "Expense",
                    "is_group": 0,
                    "disabled": 0,
                },
                pluck="name",
                order_by="name asc",
                limit=100,
            ),
            "cost_centers": frappe.get_all(
                "Cost Center",
                filters={"company": company, "is_group": 0, "disabled": 0},
                pluck="name",
                order_by="name asc",
                limit=100,
            ),
        },
        meta={"stub": False, "source": "Stock Settings"},
    )


def _validate_payload(item: dict[str, Any]) -> None:
    code = require_str(item.get("item_code") or item.get("code"), "item_code")
    name = require_str(item.get("item_name") or item.get("name") or code, "item_name")
    item["item_code"] = code
    item["item_name"] = name

    group = cstr(item.get("item_group") or "").strip()
    if not group:
        frappe.throw("Item Group is required")
    item["item_group"] = group

    uom = cstr(item.get("stock_uom") or item.get("uom") or "").strip()
    if not uom:
        frappe.throw("Stock UOM is required")
    item["stock_uom"] = uom

    for key in ("selling_rate", "purchase_rate", "standard_rate", "valuation_rate"):
        if key in item and item[key] is not None and flt(item[key]) < 0:
            frappe.throw("Prices cannot be negative")


def _assert_no_duplicates(item: dict[str, Any], *, exclude: str | None = None) -> None:
    code = item["item_code"]
    if frappe.db.exists("Item", code) and code != exclude:
        frappe.throw(f"Duplicate Item Code — Item {code} already exists")

    barcode = cstr(item.get("barcode") or "").strip()
    if barcode and frappe.db.exists("DocType", "Item Barcode"):
        filters: dict[str, Any] = {"barcode": barcode}
        rows = frappe.get_all("Item Barcode", filters=filters, fields=["parent"], limit=5)
        for row in rows:
            if exclude and row.parent == exclude:
                continue
            frappe.throw(f"Duplicate Barcode — already used on Item {row.parent}")


def _save_attachment(
    *,
    filename: str,
    content_b64: str,
    doctype: str,
    docname: str,
    fieldname: str | None = None,
) -> str:
    raw = content_b64.strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    data = base64.b64decode(raw)
    if len(data) > 8 * 1024 * 1024:
        frappe.throw(f"Attachment {filename} exceeds 8MB limit")

    from frappe.utils.file_manager import save_file

    file_doc = save_file(
        filename,
        data,
        doctype,
        docname,
        folder=None,
        decode=False,
        is_private=0 if fieldname == "image" else 1,
        df=fieldname,
    )
    return file_doc.file_url


def _enrich_item(name: str) -> dict[str, Any]:
    doc = frappe.get_doc("Item", name)
    barcode = ""
    if getattr(doc, "barcodes", None) and doc.barcodes:
        barcode = doc.barcodes[0].barcode
    return {
        "id": doc.name,
        "name": doc.name,
        "erp_name": doc.name,
        "item_code": doc.item_code or doc.name,
        "item_name": doc.item_name,
        "item_name_ar": getattr(doc, "zatgo_item_name_ar", None),
        "item_group": doc.item_group,
        "stock_uom": doc.stock_uom,
        "sales_uom": getattr(doc, "sales_uom", None) or doc.stock_uom,
        "description": doc.description,
        "brand": doc.brand,
        "barcode": barcode,
        "sku": getattr(doc, "zatgo_sku", None),
        "hs_code": getattr(doc, "customs_tariff_number", None),
        "selling_rate": flt(doc.standard_rate),
        "purchase_rate": flt(getattr(doc, "valuation_rate", None) or 0),
        "is_stock_item": int(doc.is_stock_item or 0),
        "disabled": int(doc.disabled or 0),
        "has_batch_no": int(doc.has_batch_no or 0),
        "has_serial_no": int(doc.has_serial_no or 0),
        "weight": flt(doc.weight_per_unit),
        "weight_uom": doc.weight_uom,
        "image": doc.image,
        "client_id": getattr(doc, "zatgo_client_id", None),
    }


def sync_item_bundle(
    client_id: str,
    item: Any = None,
    attachments: Any = None,
) -> dict[str, Any]:
    """
    Idempotent Item create with optional barcode, defaults, Item Price,
    opening stock, and image/gallery uploads.
    """
    require_login()
    cid = require_str(client_id, "client_id")
    payload = _as_dict(item, "item")
    atts = _as_dict(attachments, "attachments")

    existing = _find_by_client_id(cid)
    if existing:
        return ok(
            _enrich_item(existing),
            meta={"stub": False, "idempotent": True, "created": False, "source": "Item"},
        )

    _validate_payload(payload)
    _assert_no_duplicates(payload)

    frappe.has_permission("Item", "create", throw=True)

    company = cstr(payload.get("company") or "").strip() or _default_company()
    stock_uom = cstr(payload.get("stock_uom") or "").strip() or _default_uom()
    sales_uom = cstr(payload.get("sales_uom") or payload.get("default_uom") or stock_uom).strip()
    item_group = cstr(payload.get("item_group") or "").strip() or _default_item_group()

    is_stock = 1
    if "is_stock_item" in payload or "maintain_stock" in payload:
        raw = payload.get("is_stock_item", payload.get("maintain_stock", 1))
        is_stock = 0 if str(raw).lower() in ("0", "false", "no") else 1

    disabled = 0
    if "disabled" in payload:
        disabled = 1 if str(payload.get("disabled")).lower() in ("1", "true", "yes") else 0
    elif "enabled" in payload:
        disabled = 0 if str(payload.get("enabled")).lower() in ("1", "true", "yes") else 1

    selling_rate = flt(payload.get("selling_rate") or payload.get("standard_rate") or 0)
    purchase_rate = flt(payload.get("purchase_rate") or payload.get("valuation_rate") or 0)

    doc_payload: dict[str, Any] = {
        "doctype": "Item",
        "item_code": payload["item_code"],
        "item_name": payload["item_name"],
        "item_group": item_group,
        "stock_uom": stock_uom,
        "is_stock_item": is_stock,
        "disabled": disabled,
        "standard_rate": selling_rate,
        "description": cstr(payload.get("description") or "").strip() or None,
        "brand": cstr(payload.get("brand") or "").strip() or None,
        "has_batch_no": 1 if str(payload.get("has_batch_no")).lower() in ("1", "true", "yes") else 0,
        "has_serial_no": 1
        if str(payload.get("has_serial_no")).lower() in ("1", "true", "yes")
        else 0,
        "weight_per_unit": flt(payload.get("weight") or payload.get("weight_per_unit") or 0),
        "weight_uom": cstr(payload.get("weight_uom") or "").strip() or None,
        "customs_tariff_number": cstr(payload.get("hs_code") or payload.get("customs_tariff_number") or "").strip()
        or None,
    }
    if frappe.db.has_column("Item", "sales_uom"):
        doc_payload["sales_uom"] = sales_uom
    if frappe.db.has_column("Item", "valuation_rate") and purchase_rate:
        doc_payload["valuation_rate"] = purchase_rate
    if frappe.db.has_column("Item", "zatgo_client_id"):
        doc_payload["zatgo_client_id"] = cid
    if frappe.db.has_column("Item", "zatgo_item_name_ar"):
        doc_payload["zatgo_item_name_ar"] = cstr(payload.get("item_name_ar") or "").strip() or None
    if frappe.db.has_column("Item", "zatgo_sku"):
        doc_payload["zatgo_sku"] = cstr(payload.get("sku") or "").strip() or None

    barcode = cstr(payload.get("barcode") or "").strip()
    if barcode:
        doc_payload["barcodes"] = [{"barcode": barcode, "uom": stock_uom}]

    # Item defaults (accounts / cost center / default warehouse)
    income = cstr(payload.get("income_account") or "").strip()
    expense = cstr(payload.get("expense_account") or "").strip()
    cost_center = cstr(payload.get("cost_center") or "").strip()
    default_warehouse = cstr(payload.get("opening_warehouse") or payload.get("default_warehouse") or "").strip()
    if any([income, expense, cost_center, default_warehouse]):
        row: dict[str, Any] = {"company": company}
        if default_warehouse and frappe.db.exists("Warehouse", default_warehouse):
            row["default_warehouse"] = default_warehouse
        if income and frappe.db.exists("Account", income):
            row["income_account"] = income
        if expense and frappe.db.exists("Account", expense):
            row["expense_account"] = expense
        if cost_center and frappe.db.exists("Cost Center", cost_center):
            row["buying_cost_center"] = cost_center
            row["selling_cost_center"] = cost_center
        doc_payload["item_defaults"] = [row]

    tax_template = cstr(payload.get("tax_template") or payload.get("item_tax_template") or "").strip()
    if tax_template and frappe.db.exists("Item Tax Template", tax_template):
        doc_payload["taxes"] = [{"item_tax_template": tax_template}]

    reorder = flt(payload.get("reorder_level") or 0)
    if reorder > 0 and default_warehouse and frappe.db.exists("Warehouse", default_warehouse):
        doc_payload["reorder_levels"] = [
            {
                "warehouse": default_warehouse,
                "warehouse_reorder_level": reorder,
                "warehouse_reorder_qty": reorder,
            }
        ]

    item_doc = frappe.get_doc(doc_payload)
    item_doc.insert()

    # Item Price
    price_list = cstr(payload.get("price_list") or "").strip() or (_default_price_list() or "")
    if selling_rate > 0 and price_list and frappe.db.exists("Price List", price_list):
        if not frappe.db.exists(
            "Item Price",
            {"item_code": item_doc.name, "price_list": price_list, "selling": 1},
        ):
            frappe.get_doc(
                {
                    "doctype": "Item Price",
                    "item_code": item_doc.name,
                    "price_list": price_list,
                    "price_list_rate": selling_rate,
                    "selling": 1,
                }
            ).insert(ignore_permissions=True)

    # Opening stock via Material Receipt (idempotent client id suffix)
    opening_qty = flt(payload.get("opening_quantity") or payload.get("opening_qty") or 0)
    if is_stock and opening_qty > 0 and default_warehouse:
        if not frappe.db.exists("Warehouse", default_warehouse):
            frappe.throw(f"Opening Warehouse not found: {default_warehouse}")
        from zatgo_core.services.go_van_service import adjust_stock

        adjust_stock(
            client_id=f"{cid}:opening",
            item_code=item_doc.name,
            warehouse=default_warehouse,
            qty_delta=opening_qty,
            company=company,
        )

    # Images after Item exists
    image = atts.get("image") or atts.get("item_image")
    if isinstance(image, dict) and (image.get("content_b64") or image.get("content")):
        url = _save_attachment(
            filename=cstr(image.get("filename") or "item.jpg"),
            content_b64=cstr(image.get("content_b64") or image.get("content")),
            doctype="Item",
            docname=item_doc.name,
            fieldname="image",
        )
        item_doc.db_set("image", url, update_modified=False)
    elif isinstance(image, str) and image.strip():
        item_doc.db_set("image", image.strip(), update_modified=False)

    gallery = atts.get("gallery")
    if isinstance(gallery, list):
        for idx, entry in enumerate(gallery):
            if not isinstance(entry, dict):
                continue
            content = entry.get("content_b64") or entry.get("content")
            if not content:
                continue
            _save_attachment(
                filename=cstr(entry.get("filename") or f"gallery_{idx}.jpg"),
                content_b64=cstr(content),
                doctype="Item",
                docname=item_doc.name,
                fieldname=None,
            )

    frappe.db.commit()
    return ok(
        _enrich_item(item_doc.name),
        meta={"stub": False, "created": True, "idempotent": False, "source": "Item"},
    )
