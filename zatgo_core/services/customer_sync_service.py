"""Offline-first Customer + Contact + Address sync for ERPNext v16."""

from __future__ import annotations

import base64
import re
from typing import Any

import frappe
from frappe.utils import cstr, flt

from zatgo_core.api.response import ok
from zatgo_core.api.validators import parse_json_dict, require_login, require_str
from zatgo_core.services.erpnext_writes import _default_company


_VAT_RE = re.compile(r"^3\d{14}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{6,20}$")


def _as_dict(value: Any, field: str) -> dict[str, Any]:
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    return parse_json_dict(value, field)


def _find_by_client_id(doctype: str, client_id: str) -> str | None:
    if not client_id or not frappe.db.exists("DocType", doctype):
        return None
    if not frappe.db.has_column(doctype, "zatgo_client_id"):
        return None
    return frappe.db.get_value(doctype, {"zatgo_client_id": client_id}, "name")


def _map_customer_type(raw: str | None) -> str:
    value = (raw or "Company").strip()
    lowered = value.lower()
    if lowered in ("individual", "person"):
        return "Individual"
    # "Customer" and anything else → Company (ERPNext options)
    return "Company"


def _default_customer_group() -> str:
    return frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups"


def _default_territory() -> str:
    return frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"


def _default_price_list() -> str | None:
    return frappe.db.get_single_value("Selling Settings", "selling_price_list")


def _default_currency(company: str | None = None) -> str | None:
    cur = frappe.db.get_single_value("Global Defaults", "default_currency")
    if cur:
        return cur
    company_name = company or _default_company()
    return frappe.db.get_value("Company", company_name, "default_currency")


def get_customer_defaults() -> dict[str, Any]:
    """Defaults + pick lists for VanSale customer forms."""
    require_login()
    company = _default_company()
    return ok(
        {
            "customer_group": _default_customer_group(),
            "territory": _default_territory(),
            "customer_type": "Company",
            "company": company,
            "default_currency": _default_currency(company),
            "default_price_list": _default_price_list(),
            "country": "Saudi Arabia",
            "customer_groups": frappe.get_all(
                "Customer Group", filters={"is_group": 0}, pluck="name", order_by="name asc", limit=200
            )
            or frappe.get_all("Customer Group", pluck="name", order_by="name asc", limit=200),
            "territories": frappe.get_all(
                "Territory", filters={"is_group": 0}, pluck="name", order_by="name asc", limit=200
            )
            or frappe.get_all("Territory", pluck="name", order_by="name asc", limit=200),
            "price_lists": frappe.get_all(
                "Price List", filters={"selling": 1, "enabled": 1}, pluck="name", order_by="name asc", limit=100
            ),
            "currencies": frappe.get_all("Currency", filters={"enabled": 1}, pluck="name", order_by="name asc", limit=100),
            "payment_terms_templates": frappe.get_all(
                "Payment Terms Template", pluck="name", order_by="name asc", limit=100
            ),
            "sales_persons": frappe.get_all(
                "Sales Person", filters={"enabled": 1}, pluck="name", order_by="name asc", limit=200
            )
            if frappe.db.exists("DocType", "Sales Person")
            else [],
            "industries": frappe.get_all("Industry Type", pluck="name", order_by="name asc", limit=200)
            if frappe.db.exists("DocType", "Industry Type")
            else [],
        },
        meta={"stub": False, "source": "Selling Settings"},
    )


def _validate_payload(customer: dict[str, Any]) -> None:
    name = require_str(customer.get("customer_name") or customer.get("name_en"), "customer_name")
    customer["customer_name"] = name

    mobile = cstr(customer.get("mobile_no") or customer.get("mobile") or "").strip()
    if not mobile:
        frappe.throw("Mobile Number is required")
    if not _PHONE_RE.match(mobile):
        frappe.throw("Invalid mobile / phone format")
    customer["mobile_no"] = mobile

    phone = cstr(customer.get("phone") or "").strip()
    if phone and not _PHONE_RE.match(phone):
        frappe.throw("Invalid phone format")

    email = cstr(customer.get("email") or customer.get("email_id") or "").strip()
    if email and not _EMAIL_RE.match(email):
        frappe.throw("Invalid email format")
    customer["email_id"] = email or None

    vat = cstr(customer.get("tax_id") or customer.get("vat_number") or "").strip()
    if vat:
        digits = re.sub(r"\D", "", vat)
        if not _VAT_RE.match(digits):
            frappe.throw("VAT Number must be 15 digits starting with 3 (KSA)")
        customer["tax_id"] = digits

    address_line1 = cstr(customer.get("address_line1") or "").strip()
    city = cstr(customer.get("city") or "").strip()
    country = cstr(customer.get("country") or "").strip()
    if not address_line1:
        frappe.throw("Address Line 1 is required")
    if not city:
        frappe.throw("City is required")
    if not country:
        frappe.throw("Country is required")
    customer["address_line1"] = address_line1
    customer["city"] = city
    customer["country"] = country


def _assert_no_duplicates(customer: dict[str, Any], *, exclude_customer: str | None = None) -> None:
    mobile = cstr(customer.get("mobile_no") or "").strip()
    tax_id = cstr(customer.get("tax_id") or "").strip()
    cr = cstr(customer.get("cr_number") or customer.get("zatgo_cr_number") or "").strip()

    filters_base: dict[str, Any] = {}
    if exclude_customer:
        filters_base["name"] = ["!=", exclude_customer]

    if mobile:
        found = frappe.db.get_value("Customer", {**filters_base, "mobile_no": mobile}, "name")
        if found:
            frappe.throw(f"Duplicate mobile number — already used by Customer {found}")
        contact = frappe.db.get_value("Contact", {"mobile_no": mobile}, "name")
        if contact and not exclude_customer:
            # Contact may already exist for another party
            links = frappe.get_all(
                "Dynamic Link",
                filters={"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
                fields=["link_name"],
                limit=1,
            )
            if links and links[0].link_name != exclude_customer:
                frappe.throw(f"Duplicate mobile number — linked to Customer {links[0].link_name}")

    if tax_id:
        found = frappe.db.get_value("Customer", {**filters_base, "tax_id": tax_id}, "name")
        if found:
            frappe.throw(f"Duplicate VAT Number — already used by Customer {found}")

    if cr and frappe.db.has_column("Customer", "zatgo_cr_number"):
        found = frappe.db.get_value("Customer", {**filters_base, "zatgo_cr_number": cr}, "name")
        if found:
            frappe.throw(f"Duplicate CR Number — already used by Customer {found}")


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
        is_private=1,
        df=fieldname,
    )
    return file_doc.file_url


def _enrich_bundle(customer_name: str) -> dict[str, Any]:
    from zatgo_core.services.erpnext_reads import enrich_customer_doc

    doc = frappe.get_doc("Customer", customer_name)
    data = enrich_customer_doc(doc)
    data["erp_name"] = doc.name
    data["client_id"] = getattr(doc, "zatgo_client_id", None)
    data["customer_name_ar"] = getattr(doc, "zatgo_customer_name_ar", None)
    data["tax_id"] = doc.tax_id
    data["cr_number"] = getattr(doc, "zatgo_cr_number", None)
    data["website"] = doc.website
    data["industry"] = doc.industry
    data["default_currency"] = doc.default_currency
    data["default_price_list"] = doc.default_price_list
    data["payment_terms"] = doc.payment_terms
    data["disabled"] = int(doc.disabled or 0)
    data["enabled"] = 0 if int(doc.disabled or 0) else 1
    data["remarks"] = doc.customer_details
    data["primary_contact"] = doc.customer_primary_contact
    data["primary_address"] = doc.customer_primary_address
    data["image"] = doc.image
    data["zatgo_cr_image"] = getattr(doc, "zatgo_cr_image", None)
    data["zatgo_vat_certificate"] = getattr(doc, "zatgo_vat_certificate", None)
    data["zatgo_customer_photo"] = getattr(doc, "zatgo_customer_photo", None)
    data["google_map_url"] = getattr(doc, "zatgo_google_map_url", None)
    return data


def sync_customer_bundle(
    client_id: str,
    customer: Any = None,
    contact: Any = None,
    address: Any = None,
    attachments: Any = None,
) -> dict[str, Any]:
    """
    Idempotent Customer create with Contact + Address + optional attachments.

    Payload keys (customer):
      customer_name, customer_name_ar, customer_type, customer_group, territory,
      tax_id, cr_number, customer_code, website, industry,
      mobile_no, phone, email,
      address_line1, address_line2, city, state, country, pincode,
      google_map_url, latitude, longitude,
      default_price_list, sales_person, credit_limit, payment_terms, default_currency,
      disabled, remarks, company
    """
    require_login()
    cid = require_str(client_id, "client_id")
    cust = _as_dict(customer, "customer")
    cont = _as_dict(contact, "contact")
    addr = _as_dict(address, "address")
    atts = _as_dict(attachments, "attachments")

    # Merge nested address/contact into customer when sent flattened
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

    existing = _find_by_client_id("Customer", cid)
    if existing:
        return ok(
            _enrich_bundle(existing),
            meta={"stub": False, "idempotent": True, "created": False, "source": "Customer"},
        )

    _validate_payload(cust)
    _assert_no_duplicates(cust)

    frappe.has_permission("Customer", "create", throw=True)

    company = cstr(cust.get("company") or "").strip() or _default_company()
    customer_type = _map_customer_type(cust.get("customer_type"))
    customer_group = cstr(cust.get("customer_group") or "").strip() or _default_customer_group()
    territory = cstr(cust.get("territory") or "").strip() or _default_territory()
    currency = cstr(cust.get("default_currency") or "").strip() or _default_currency(company)
    price_list = cstr(cust.get("default_price_list") or "").strip() or (_default_price_list() or "")
    if "disabled" in cust:
        disabled = 1 if str(cust.get("disabled")).lower() in ("1", "true", "yes") else 0
    elif "enabled" in cust:
        disabled = 0 if str(cust.get("enabled")).lower() in ("1", "true", "yes") else 1
    else:
        disabled = 0

    doc_payload: dict[str, Any] = {
        "doctype": "Customer",
        "customer_name": cust["customer_name"],
        "customer_type": customer_type,
        "customer_group": customer_group,
        "territory": territory,
        "tax_id": cust.get("tax_id") or None,
        "website": cstr(cust.get("website") or "").strip() or None,
        "mobile_no": cust.get("mobile_no"),
        "email_id": cust.get("email_id"),
        "default_currency": currency or None,
        "default_price_list": price_list or None,
        "payment_terms": cstr(cust.get("payment_terms") or "").strip() or None,
        "disabled": disabled,
        "customer_details": cstr(cust.get("remarks") or "").strip() or None,
    }
    industry = cstr(cust.get("industry") or "").strip()
    if industry and frappe.db.exists("Industry Type", industry):
        doc_payload["industry"] = industry
    elif industry and frappe.db.exists("DocType", "Industry Type"):
        # Ignore unknown industry labels rather than failing the whole sync.
        pass
    if frappe.db.has_column("Customer", "zatgo_client_id"):
        doc_payload["zatgo_client_id"] = cid
    if frappe.db.has_column("Customer", "zatgo_customer_name_ar"):
        doc_payload["zatgo_customer_name_ar"] = cstr(cust.get("customer_name_ar") or "").strip() or None
    if frappe.db.has_column("Customer", "zatgo_cr_number"):
        doc_payload["zatgo_cr_number"] = cstr(cust.get("cr_number") or "").strip() or None
    if frappe.db.has_column("Customer", "zatgo_google_map_url"):
        doc_payload["zatgo_google_map_url"] = cstr(cust.get("google_map_url") or "").strip() or None

    # Optional naming / code
    _ = cstr(cust.get("customer_code") or "").strip()

    credit_limit = flt(cust.get("credit_limit") or 0)
    if credit_limit > 0:
        doc_payload["credit_limits"] = [
            {"company": company, "credit_limit": credit_limit, "bypass_credit_limit_check": 0}
        ]

    sales_person = cstr(cust.get("sales_person") or "").strip()
    if sales_person and frappe.db.exists("Sales Person", sales_person):
        doc_payload["sales_team"] = [{"sales_person": sales_person, "allocated_percentage": 100}]

    customer_doc = frappe.get_doc(doc_payload)
    customer_doc.insert()

    # Contact
    contact_client_id = f"{cid}:contact"
    contact_name = _find_by_client_id("Contact", contact_client_id)
    if not contact_name:
        frappe.has_permission("Contact", "create", throw=True)
        first = cust["customer_name"]
        contact_doc = frappe.get_doc(
            {
                "doctype": "Contact",
                "first_name": first[:140],
                "mobile_no": cust.get("mobile_no"),
                "phone": cstr(cust.get("phone") or "").strip() or None,
                "email_id": cust.get("email_id"),
                "is_primary_contact": 1,
                "links": [{"link_doctype": "Customer", "link_name": customer_doc.name}],
            }
        )
        if cust.get("email_id"):
            contact_doc.append(
                "email_ids",
                {"email_id": cust["email_id"], "is_primary": 1},
            )
        if cust.get("mobile_no"):
            contact_doc.append(
                "phone_nos",
                {"phone": cust["mobile_no"], "is_primary_mobile_no": 1},
            )
        phone = cstr(cust.get("phone") or "").strip()
        if phone and phone != cust.get("mobile_no"):
            contact_doc.append("phone_nos", {"phone": phone, "is_primary_phone": 1})
        if frappe.db.has_column("Contact", "zatgo_client_id"):
            contact_doc.zatgo_client_id = contact_client_id
        contact_doc.insert()
        contact_name = contact_doc.name
        customer_doc.db_set("customer_primary_contact", contact_name, update_modified=False)

    # Address
    address_client_id = f"{cid}:address"
    address_name = _find_by_client_id("Address", address_client_id)
    if not address_name:
        frappe.has_permission("Address", "create", throw=True)
        address_doc = frappe.get_doc(
            {
                "doctype": "Address",
                "address_title": cust["customer_name"][:140],
                "address_type": "Billing",
                "address_line1": cust["address_line1"],
                "address_line2": cstr(cust.get("address_line2") or "").strip() or None,
                "city": cust["city"],
                "state": cstr(cust.get("state") or "").strip() or None,
                "country": cust["country"],
                "pincode": cstr(cust.get("pincode") or cust.get("postal_code") or "").strip() or None,
                "phone": cust.get("mobile_no"),
                "email_id": cust.get("email_id"),
                "is_primary_address": 1,
                "is_shipping_address": 1,
                "links": [{"link_doctype": "Customer", "link_name": customer_doc.name}],
            }
        )
        if frappe.db.has_column("Address", "zatgo_client_id"):
            address_doc.zatgo_client_id = address_client_id
        if frappe.db.has_column("Address", "zatgo_latitude"):
            address_doc.zatgo_latitude = flt(cust.get("latitude") or 0) or None
        if frappe.db.has_column("Address", "zatgo_longitude"):
            address_doc.zatgo_longitude = flt(cust.get("longitude") or 0) or None
        if frappe.db.has_column("Address", "zatgo_google_map_url"):
            address_doc.zatgo_google_map_url = cstr(cust.get("google_map_url") or "").strip() or None
        address_doc.insert()
        address_name = address_doc.name
        customer_doc.db_set("customer_primary_address", address_name, update_modified=False)

    # Attachments (base64)
    field_map = {
        "cr_image": "zatgo_cr_image",
        "vat_certificate": "zatgo_vat_certificate",
        "customer_photo": "zatgo_customer_photo",
        "image": "image",
    }
    for key, fieldname in field_map.items():
        item = atts.get(key)
        if not item:
            continue
        if isinstance(item, str):
            # already a file URL
            if frappe.db.has_column("Customer", fieldname) or fieldname == "image":
                customer_doc.db_set(fieldname, item, update_modified=False)
            continue
        if not isinstance(item, dict):
            continue
        content = item.get("content_b64") or item.get("content")
        filename = cstr(item.get("filename") or f"{key}.jpg")
        if not content:
            continue
        if not (frappe.db.has_column("Customer", fieldname) or fieldname == "image"):
            continue
        url = _save_attachment(
            filename=filename,
            content_b64=cstr(content),
            doctype="Customer",
            docname=customer_doc.name,
            fieldname=fieldname,
        )
        customer_doc.db_set(fieldname, url, update_modified=False)

    frappe.db.commit()
    return ok(
        {
            **_enrich_bundle(customer_doc.name),
            "contact": contact_name,
            "address": address_name,
        },
        meta={
            "stub": False,
            "created": True,
            "idempotent": False,
            "source": "Customer",
            "linked": {"contact": contact_name, "address": address_name},
        },
    )
