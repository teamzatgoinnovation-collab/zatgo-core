"""Conflict-aware Customer sync ops (create / update / delete) for VanSale."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cstr, get_datetime

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login, require_str
from zatgo_core.services.customer_sync_service import (
    _assert_no_duplicates,
    _as_dict,
    _enrich_bundle,
    _find_by_client_id,
    _save_attachment,
    _validate_payload,
    sync_customer_bundle,
)


def _modified_str(doc: Any) -> str:
    return cstr(doc.modified)


def _conflict_response(docname: str, *, client_id: str, base_modified: str | None) -> dict[str, Any]:
    data = _enrich_bundle(docname)
    data["modified"] = _modified_str(frappe.get_doc("Customer", docname))
    data["base_modified"] = base_modified
    data["conflict"] = True
    return ok(
        data,
        meta={
            "stub": False,
            "conflict": True,
            "source": "Customer",
            "message": "Server copy is newer; resolve conflict before syncing.",
        },
    )


def _apply_customer_fields(doc: Any, cust: dict[str, Any]) -> None:
    mapping = {
        "customer_name": "customer_name",
        "customer_type": "customer_type",
        "customer_group": "customer_group",
        "territory": "territory",
        "tax_id": "tax_id",
        "website": "website",
        "industry": "industry",
        "mobile_no": "mobile_no",
        "email_id": "email_id",
        "email": "email_id",
        "default_currency": "default_currency",
        "default_price_list": "default_price_list",
        "payment_terms": "payment_terms",
        "customer_details": "customer_details",
        "remarks": "customer_details",
    }
    for src, field in mapping.items():
        if src in cust and cust[src] is not None:
            setattr(doc, field, cust[src] if cust[src] != "" else None)
    if "disabled" in cust:
        doc.disabled = 1 if str(cust.get("disabled")).lower() in ("1", "true", "yes") else 0
    elif "enabled" in cust:
        doc.disabled = 0 if str(cust.get("enabled")).lower() in ("1", "true", "yes") else 1
    if frappe.db.has_column("Customer", "zatgo_customer_name_ar") and "customer_name_ar" in cust:
        doc.zatgo_customer_name_ar = cstr(cust.get("customer_name_ar") or "") or None
    if frappe.db.has_column("Customer", "zatgo_cr_number") and "cr_number" in cust:
        doc.zatgo_cr_number = cstr(cust.get("cr_number") or "") or None
    if frappe.db.has_column("Customer", "zatgo_google_map_url") and "google_map_url" in cust:
        doc.zatgo_google_map_url = cstr(cust.get("google_map_url") or "") or None


def _sync_contact_address(customer_name: str, cid: str, cust: dict[str, Any], atts: dict[str, Any]) -> None:
    # Update primary contact / address when present
    contact_name = frappe.db.get_value("Customer", customer_name, "customer_primary_contact")
    if contact_name and frappe.db.exists("Contact", contact_name):
        cdoc = frappe.get_doc("Contact", contact_name)
        if cust.get("mobile_no"):
            cdoc.mobile_no = cust["mobile_no"]
        if cust.get("phone"):
            cdoc.phone = cust["phone"]
        if cust.get("email_id") or cust.get("email"):
            cdoc.email_id = cust.get("email_id") or cust.get("email")
        cdoc.save(ignore_permissions=True)

    address_name = frappe.db.get_value("Customer", customer_name, "customer_primary_address")
    if address_name and frappe.db.exists("Address", address_name):
        adoc = frappe.get_doc("Address", address_name)
        for field, key in (
            ("address_line1", "address_line1"),
            ("address_line2", "address_line2"),
            ("city", "city"),
            ("state", "state"),
            ("country", "country"),
            ("pincode", "pincode"),
        ):
            if cust.get(key):
                setattr(adoc, field, cust[key])
        if frappe.db.has_column("Address", "zatgo_latitude") and cust.get("latitude") is not None:
            adoc.zatgo_latitude = cust.get("latitude")
        if frappe.db.has_column("Address", "zatgo_longitude") and cust.get("longitude") is not None:
            adoc.zatgo_longitude = cust.get("longitude")
        adoc.save(ignore_permissions=True)

    field_map = {
        "cr_image": "zatgo_cr_image",
        "vat_certificate": "zatgo_vat_certificate",
        "customer_photo": "zatgo_customer_photo",
        "image": "image",
    }
    for key, fieldname in field_map.items():
        item = atts.get(key)
        if not item or not isinstance(item, dict):
            continue
        content = item.get("content_b64") or item.get("content")
        if not content:
            continue
        if not (frappe.db.has_column("Customer", fieldname) or fieldname == "image"):
            continue
        url = _save_attachment(
            filename=cstr(item.get("filename") or f"{key}.jpg"),
            content_b64=cstr(content),
            doctype="Customer",
            docname=customer_name,
            fieldname=fieldname,
        )
        frappe.db.set_value("Customer", customer_name, fieldname, url, update_modified=False)


def sync_customer_op(
    client_id: str,
    op: str = "create",
    customer: Any = None,
    contact: Any = None,
    address: Any = None,
    attachments: Any = None,
    base_modified: str | None = None,
    force: int | str | bool | None = 0,
) -> dict[str, Any]:
    """
    Create / update / delete (disable) Customer with modified-timestamp conflict detection.

    Never creates duplicates: create is idempotent on zatgo_client_id.
    """
    require_login()
    cid = require_str(client_id, "client_id")
    operation = cstr(op or "create").strip().lower()
    force_flag = str(force).lower() in ("1", "true", "yes")

    if operation in ("create", "upsert") and not _find_by_client_id("Customer", cid):
        result = sync_customer_bundle(
            client_id=cid,
            customer=customer,
            contact=contact,
            address=address,
            attachments=attachments,
        )
        # Attach modified
        name = (result.get("data") or {}).get("erp_name") or (result.get("data") or {}).get("id")
        if name:
            result["data"]["modified"] = frappe.db.get_value("Customer", name, "modified")
        return result

    existing = _find_by_client_id("Customer", cid)
    if not existing:
        # Fall back to create if update/delete without local ERP link
        if operation == "delete":
            return ok(
                {"client_id": cid, "deleted": False, "missing": True},
                meta={"stub": False, "idempotent": True, "source": "Customer"},
            )
        return sync_customer_bundle(
            client_id=cid,
            customer=customer,
            contact=contact,
            address=address,
            attachments=attachments,
        )

    doc = frappe.get_doc("Customer", existing)
    server_modified = _modified_str(doc)
    if (
        not force_flag
        and base_modified
        and get_datetime(base_modified)
        and get_datetime(server_modified)
        and get_datetime(server_modified) > get_datetime(base_modified)
        and operation in ("update", "upsert", "delete")
    ):
        return _conflict_response(existing, client_id=cid, base_modified=base_modified)

    if operation == "delete":
        frappe.has_permission("Customer", "write", doc=existing, throw=True)
        doc.disabled = 1
        doc.save()
        frappe.db.commit()
        data = _enrich_bundle(doc.name)
        data["modified"] = _modified_str(doc)
        data["deleted"] = True
        return ok(data, meta={"stub": False, "disabled": True, "source": "Customer"})

    # update
    frappe.has_permission("Customer", "write", doc=existing, throw=True)
    cust = _as_dict(customer, "customer")
    cont = _as_dict(contact, "contact")
    addr = _as_dict(address, "address")
    atts = _as_dict(attachments, "attachments")
    for key in (
        "address_line1",
        "address_line2",
        "city",
        "state",
        "country",
        "pincode",
        "latitude",
        "longitude",
        "google_map_url",
    ):
        if key not in cust and key in addr:
            cust[key] = addr[key]
    for key in ("mobile_no", "phone", "email", "email_id"):
        if key not in cust and key in cont:
            cust[key] = cont[key]

    if cust:
        _validate_payload({**cust, "customer_name": cust.get("customer_name") or doc.customer_name})
        _assert_no_duplicates(cust, exclude_customer=existing)
        _apply_customer_fields(doc, cust)
        doc.save()
    _sync_contact_address(existing, cid, cust, atts)
    frappe.db.commit()
    data = _enrich_bundle(existing)
    data["modified"] = frappe.db.get_value("Customer", existing, "modified")
    return ok(data, meta={"stub": False, "updated": True, "source": "Customer"})
