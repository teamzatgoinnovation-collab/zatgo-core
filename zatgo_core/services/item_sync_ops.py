"""Conflict-aware Item sync ops (create / update / delete) for VanSale."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cstr, flt, get_datetime

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login, require_str
from zatgo_core.services.item_sync_service import (
    _assert_no_duplicates,
    _as_dict,
    _enrich_item,
    _find_by_client_id,
    _save_attachment,
    _validate_payload,
    sync_item_bundle,
)


def _conflict_response(name: str, *, base_modified: str | None) -> dict[str, Any]:
    data = _enrich_item(name)
    data["modified"] = cstr(frappe.db.get_value("Item", name, "modified"))
    data["base_modified"] = base_modified
    data["conflict"] = True
    return ok(
        data,
        meta={
            "stub": False,
            "conflict": True,
            "source": "Item",
            "message": "Server Item is newer; resolve conflict before syncing.",
        },
    )


def sync_item_op(
    client_id: str,
    op: str = "create",
    item: Any = None,
    attachments: Any = None,
    base_modified: str | None = None,
    force: int | str | bool | None = 0,
) -> dict[str, Any]:
    require_login()
    cid = require_str(client_id, "client_id")
    operation = cstr(op or "create").strip().lower()
    force_flag = str(force).lower() in ("1", "true", "yes")

    existing = _find_by_client_id(cid)
    if operation in ("create", "upsert") and not existing:
        result = sync_item_bundle(client_id=cid, item=item, attachments=attachments)
        name = (result.get("data") or {}).get("erp_name") or (result.get("data") or {}).get("item_code")
        if name:
            result["data"]["modified"] = frappe.db.get_value("Item", name, "modified")
        return result

    if not existing:
        if operation == "delete":
            return ok(
                {"client_id": cid, "deleted": False, "missing": True},
                meta={"stub": False, "idempotent": True, "source": "Item"},
            )
        return sync_item_bundle(client_id=cid, item=item, attachments=attachments)

    doc = frappe.get_doc("Item", existing)
    server_modified = cstr(doc.modified)
    if (
        not force_flag
        and base_modified
        and get_datetime(base_modified)
        and get_datetime(server_modified)
        and get_datetime(server_modified) > get_datetime(base_modified)
        and operation in ("update", "upsert", "delete")
    ):
        return _conflict_response(existing, base_modified=base_modified)

    if operation == "delete":
        frappe.has_permission("Item", "write", doc=existing, throw=True)
        doc.disabled = 1
        doc.save()
        frappe.db.commit()
        data = _enrich_item(doc.name)
        data["modified"] = cstr(doc.modified)
        data["deleted"] = True
        return ok(data, meta={"stub": False, "disabled": True, "source": "Item"})

    frappe.has_permission("Item", "write", doc=existing, throw=True)
    payload = _as_dict(item, "item")
    atts = _as_dict(attachments, "attachments")
    if payload:
        # Keep existing code for validation identity
        payload.setdefault("item_code", doc.item_code or doc.name)
        payload.setdefault("item_name", doc.item_name)
        payload.setdefault("item_group", doc.item_group)
        payload.setdefault("stock_uom", doc.stock_uom)
        _validate_payload(payload)
        _assert_no_duplicates(payload, exclude=existing)
        if payload.get("item_name"):
            doc.item_name = payload["item_name"]
        if payload.get("item_group"):
            doc.item_group = payload["item_group"]
        if payload.get("description") is not None:
            doc.description = payload.get("description") or None
        if payload.get("brand") is not None:
            doc.brand = payload.get("brand") or None
        if "selling_rate" in payload or "standard_rate" in payload:
            doc.standard_rate = flt(payload.get("selling_rate") or payload.get("standard_rate") or 0)
        if "disabled" in payload:
            doc.disabled = 1 if str(payload.get("disabled")).lower() in ("1", "true", "yes") else 0
        if frappe.db.has_column("Item", "zatgo_item_name_ar") and "item_name_ar" in payload:
            doc.zatgo_item_name_ar = cstr(payload.get("item_name_ar") or "") or None
        if frappe.db.has_column("Item", "zatgo_sku") and "sku" in payload:
            doc.zatgo_sku = cstr(payload.get("sku") or "") or None
        doc.save()

    image = atts.get("image") or atts.get("item_image")
    if isinstance(image, dict) and (image.get("content_b64") or image.get("content")):
        url = _save_attachment(
            filename=cstr(image.get("filename") or "item.jpg"),
            content_b64=cstr(image.get("content_b64") or image.get("content")),
            doctype="Item",
            docname=doc.name,
            fieldname="image",
        )
        doc.db_set("image", url, update_modified=False)

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
                docname=doc.name,
                fieldname=None,
            )

    frappe.db.commit()
    data = _enrich_item(existing)
    data["modified"] = frappe.db.get_value("Item", existing, "modified")
    return ok(data, meta={"stub": False, "updated": True, "source": "Item"})
