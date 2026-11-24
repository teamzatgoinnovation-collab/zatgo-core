"""Licence API (customer sites) and licence issuing API (the issuer site).

Paths: zatgo_core.api.v1.licensing.licences.<method>

Customer site: a System Manager reads the site identity (to request a licence), imports a licence or a
revocation list, and re-verifies the licence in force; readers of ZG Licence see the summary.
Issuer site (site_config `zg_licence_issuer`, System Manager): issue, list, revoke. Writes are POST only.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_str
from zatgo_core.licensing import entitlement, issuing, licences, site_identity


def _require_system_manager() -> None:
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only a System Manager can manage the licence."), frappe.PermissionError)


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        parsed = frappe.parse_json(value) if value.strip().startswith("[") else value.replace(",", "\n").splitlines()
        value = parsed
    return [str(v).strip() for v in (value or []) if str(v).strip()]


# -- customer site --------------------------------------------------------------------------------------------

@frappe.whitelist()
def site_identity_info() -> dict[str, Any]:
    """What the issuer needs to bind a licence to this site. Creates the site ID the first time."""
    _require_system_manager()
    return ok(site_identity.identity(create=True))


@frappe.whitelist()
def current_licence() -> dict[str, Any]:
    if not frappe.has_permission(licences.DOCTYPE, "read"):
        frappe.throw(_("Not permitted to read the licence."), frappe.PermissionError)
    return ok({**licences.summary(), "enforcement": entitlement.describe()})


@frappe.whitelist(methods=["POST"])
def import_licence(file: str) -> dict[str, Any]:
    _require_system_manager()
    site_identity.site_id(create=True)
    return ok(licences.import_licence(require_str(file, "file")))


@frappe.whitelist(methods=["POST"])
def import_revocation(file: str) -> dict[str, Any]:
    _require_system_manager()
    return ok(licences.import_revocation(require_str(file, "file")))


@frappe.whitelist(methods=["POST"])
def verify_licence() -> dict[str, Any]:
    """Re-check the licence in force from its signed file (signature, site binding)."""
    _require_system_manager()
    doc = licences.current_doc()
    if doc is None:
        return ok({"present": False})
    result = licences.verify_stored(doc)
    licences.clear_cache()
    if result["ok"]:
        frappe.db.set_value(licences.DOCTYPE, doc.name, "verified_on", frappe.utils.now_datetime(),
                            update_modified=False)
    else:
        from zatgo_core.licensing import audit

        audit.log("licence_verification_failed", licences.DOCTYPE, doc.name, {"code": result["code"]},
                  reason=result["message"] or "")
    return ok({"present": True, "ok": result["ok"], "code": result["code"], "message": result["message"]})


# -- issuer site --------------------------------------------------------------------------------------------

@frappe.whitelist(methods=["POST"])
def issue_licence(edition_id: str, customer_name: str, site_ids: Any, customer_id: str = "", site_names: Any = None,
                  licence_type: str | None = None, start_date: str | None = None, expiry_date: str | None = None,
                  duration_days: Any = None, max_users: Any = None, max_companies: Any = None,
                  max_sites: Any = None, grace_days: Any = 0, replaces: str | None = None) -> dict[str, Any]:
    limits = {k: int(v) for k, v in (("max_users", max_users), ("max_companies", max_companies),
                                       ("max_sites", max_sites)) if v not in (None, "")}
    return ok(issuing.issue(
        require_str(edition_id, "edition_id"), require_str(customer_name, "customer_name"), _list(site_ids),
        customer_id=customer_id or "", site_names=_list(site_names), licence_type=licence_type or None,
        start_date=start_date or None, expiry_date=expiry_date or None,
        duration_days=int(duration_days) if duration_days not in (None, "") else None,
        limits=limits, grace_days=int(grace_days or 0), replaces=replaces or None,
    ))


@frappe.whitelist()
def issued_licences() -> dict[str, Any]:
    return ok(issuing.history())


@frappe.whitelist(methods=["POST"])
def revoke_licences(licence_ids: Any) -> dict[str, Any]:
    return ok(issuing.revocation_list(_list(licence_ids)))


# -- the Licence page (zg-licence) ----------------------------------------------------------------------------

@frappe.whitelist()
def get_page() -> dict[str, Any]:
    """Everything the Licence page shows. Readers of ZG Licence see it; actions are for a System Manager."""
    if not frappe.has_permission(licences.DOCTYPE, "read"):
        frappe.throw(_("Not permitted to read the licence."), frappe.PermissionError)
    from zatgo_core.licensing import editions, issuer, licence_overview
    from zatgo_core.services.ui_apps import asset_url

    is_manager = frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()
    data = {**licence_overview.overview(), "can_manage": is_manager, "is_issuer": issuer.is_issuer_site(),
            "history": licence_overview.history(), "css": asset_url("css/zg_licence.css")}
    if data["is_issuer"] and is_manager:
        data["issuer"] = {
            "editions": [e for e in editions.list_editions() if e["status"] == "Active"],
            "issued": issuing.history(),
            "licence_types": list(editions.edition_config.LICENCE_TYPES),
        }
    return ok(data)


@frappe.whitelist()
def site_request() -> dict[str, Any]:
    """The file to send ZatGo to get a licence for this site."""
    _require_system_manager()
    from zatgo_core.licensing import licence_overview

    return ok(licence_overview.site_request())


@frappe.whitelist()
def licence_info() -> dict[str, Any]:
    """Licence metadata export / backup (not a licence; cannot be imported)."""
    _require_system_manager()
    from zatgo_core.licensing import licence_overview

    return ok(licence_overview.licence_info())


@frappe.whitelist()
def download_licence(name: str) -> dict[str, Any]:
    """The signed file of an imported licence, to keep a copy."""
    _require_system_manager()
    from zatgo_core.licensing import licence_overview

    return ok(licence_overview.licence_file(require_str(name, "name")))


@frappe.whitelist()
def download_issued(licence_number: str) -> dict[str, Any]:
    """Issuer site: the signed file of a licence issued here, to send again."""
    from zatgo_core.licensing import issuer

    issuer.require_issuer_manager()
    doc = frappe.get_doc(issuing.HISTORY, require_str(licence_number, "licence_number"))
    return ok({"filename": f"{doc.licence_number}.zglicence", "file": doc.licence_file})
