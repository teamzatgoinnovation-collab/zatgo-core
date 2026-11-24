"""Licences on a customer site: import, verification, revocation, and the entitlement they give (Phase 5).

Import (brief Part 8):
  parse -> verify the Ed25519 signature with a key this app version trusts -> validate schema / product /
  dates / features -> check the site binding (this site's `zg_site_id`, and its name when the licence lists
  names) -> refuse a licence that has not started, has expired, was revoked, or is older than the one in force
  -> store the original signed file in `ZG Licence` (the new one becomes current) -> drop the cached
  entitlement -> audit. Every refusal is audited too, with its reason code.

Trust: only the stored signed file counts. The current licence is re-verified (signature, site) whenever the
cached entitlement is rebuilt, so editing a `ZG Licence` row in the database grants nothing; a row that no longer
verifies gives the foundation only.

Offline limits, documented rather than hidden: there is no central revocation -- a signed revocation list or a
replacement licence (higher `licence_version`) is imported like a licence; expiry and clock-rollback handling
belong to Phase 7.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime, today

from zatgo_core.licensing import audit, licence_format, site_identity
from zatgo_core.licensing.entitlement import Entitlement
from zatgo_core.licensing.licence_format import LicenceError

DOCTYPE = "ZG Licence"
CACHE_KEY = "zg_licence_entitlement"


def refuse_manual_change(doc: Any) -> None:
    """Controller guard of ZG Licence / ZG Licence History: only the licensing services write them."""
    flags = frappe.flags
    if flags.in_licence_write or flags.in_install or flags.in_migrate or flags.in_patch:
        return
    frappe.throw(_("{0} records are written by the licensing service only.").format(_(doc.doctype)),
                 frappe.PermissionError)


def _write(fn, *args, **kwargs):
    previous = frappe.flags.in_licence_write
    frappe.flags.in_licence_write = True
    try:
        return fn(*args, **kwargs)
    finally:
        frappe.flags.in_licence_write = previous


def clear_cache() -> None:
    frappe.cache.delete_value(CACHE_KEY)
    for attr in ("zg_licence_entitlement", "zg_licence_data", "zg_licence_hwm"):
        if hasattr(frappe.local, attr):
            delattr(frappe.local, attr)


# -- checks ---------------------------------------------------------------------------------------------------

def _check_site(payload: dict[str, Any]) -> None:
    sid = site_identity.site_id()
    if not sid or sid not in payload["site_ids"]:
        raise LicenceError("wrong_site", "this licence is for another site (its site ID does not match this site's)")
    names = payload.get("site_names") or []
    if names and site_identity.site_name() not in names:
        raise LicenceError("wrong_site", f"this licence is for {', '.join(names)}, not {site_identity.site_name()}")


def _check_time(payload: dict[str, Any], on: date) -> str:
    state = licence_format.status(payload, on)
    if state == "Scheduled":
        raise LicenceError("not_yet_valid", f"this licence starts on {payload['start_date']}")
    if state == "Expired":
        raise LicenceError("expired", f"this licence expired on {payload['expiry_date']}")
    return state


def _check_history(payload: dict[str, Any], digest: str) -> None:
    if frappe.db.exists(DOCTYPE, digest):
        raise LicenceError("already_imported", "this licence file is already imported")
    rows = frappe.get_all(DOCTYPE, filters={"licence_id": payload["licence_id"]},
                          fields=["licence_version", "revoked_on", "status"])
    if any(r.revoked_on or r.status == "Revoked" for r in rows):
        raise LicenceError("revoked", "this licence was revoked")
    newest = max((cint(r.licence_version) for r in rows), default=0)
    if payload["licence_version"] <= newest:
        raise LicenceError("outdated",
                           f"a newer version ({newest}) of this licence is already imported; this file is version {payload['licence_version']}")


# -- import ---------------------------------------------------------------------------------------------------

def import_licence(text: str | bytes) -> dict[str, Any]:
    """Verify and install a licence file. Raises frappe.ValidationError (with the reason) when refused."""
    try:
        payload, raw, envelope = licence_format.open_envelope(text)
        licence_format.validate_payload(payload)
        _check_site(payload)
        state = _check_time(payload, getdate(today()))
        digest = licence_format.payload_hash(raw)
        _check_history(payload, digest)
    except LicenceError as exc:
        audit.log("licence_rejected", DOCTYPE, None, {"code": exc.code}, reason=str(exc), durable=True)
        frappe.throw(_("Licence refused: {0}").format(str(exc)), title=_("Licence not imported"))

    previous = frappe.db.get_value(DOCTYPE, {"is_current": 1}, ["name", "licence_number"], as_dict=True)
    doc = _write(_store, payload, raw, envelope, digest, state)
    audit.log("licence_imported", DOCTYPE, doc.name,
              {"licence_number": doc.licence_number, "licence_id": doc.licence_id, "version": doc.licence_version,
               "edition": doc.edition_id, "replaces": previous.licence_number if previous else None})
    clear_cache()
    return summary(doc)


def _store(payload, raw, envelope, digest, state):
    frappe.db.set_value(DOCTYPE, {"is_current": 1}, "is_current", 0, update_modified=False)
    limits = payload.get("limits") or {}
    doc = frappe.get_doc({
        "doctype": DOCTYPE,
        "payload_hash": digest,
        "licence_id": payload["licence_id"],
        "licence_number": payload["licence_number"],
        "licence_version": payload["licence_version"],
        "customer_id": payload.get("customer_id") or "",
        "customer_name": payload["customer_name"],
        "edition_id": payload["edition_id"],
        "edition_name": payload["edition_name"],
        "edition_version": payload["edition_version"],
        "licence_type": payload["licence_type"],
        "status": state,
        "is_current": 1,
        "issue_date": payload["issue_date"],
        "start_date": payload["start_date"],
        "expiry_date": payload["expiry_date"],
        "max_users": limits.get("max_users", 0),
        "max_companies": limits.get("max_companies", 0),
        "max_sites": limits.get("max_sites", 0),
        "site_ids": "\n".join(payload["site_ids"]),
        "site_names": "\n".join(payload.get("site_names") or []),
        "feature_count": len(payload["features"]),
        "key_id": envelope["key_id"],
        "imported_by": frappe.session.user,
        "imported_on": now_datetime(),
        "verified_on": now_datetime(),
        "payload_json": json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False),
        "licence_file": json.dumps(envelope, indent=1, sort_keys=True),
    })
    doc.insert(ignore_permissions=True)
    return doc


# -- revocation -----------------------------------------------------------------------------------------------

def import_revocation(text: str | bytes) -> dict[str, Any]:
    """A signed revocation list from the issuer: the licences it names stop counting here."""
    try:
        payload, raw, _envelope = licence_format.open_envelope(text, kind=licence_format.REVOCATION_TYPE)
        revoked = licence_format.validate_revocation(payload)
    except LicenceError as exc:
        audit.log("revocation_rejected", DOCTYPE, None, {"code": exc.code}, reason=str(exc), durable=True)
        frappe.throw(_("Revocation list refused: {0}").format(str(exc)), title=_("Not imported"))
    names = frappe.get_all(DOCTYPE, filters={"licence_id": ["in", revoked or ["-"]], "revoked_on": ["is", "not set"]},
                           pluck="name")

    def _revoke():
        for name in names:
            frappe.db.set_value(DOCTYPE, name, {"status": "Revoked", "revoked_on": now_datetime()},
                                update_modified=False)

    _write(_revoke)
    audit.log("licences_revoked", DOCTYPE, None,
              {"listed": len(revoked), "revoked_here": names, "list_hash": licence_format.payload_hash(raw)})
    clear_cache()
    return {"listed": len(revoked), "revoked": names}


# -- the licence in force -------------------------------------------------------------------------------------

def current_doc():
    name = frappe.db.get_value(DOCTYPE, {"is_current": 1}, "name")
    return frappe.get_doc(DOCTYPE, name) if name else None


def verify_stored(doc) -> dict[str, Any]:
    """Re-check a stored licence from its signed file alone. {"ok", "code", "message", "payload"}."""
    try:
        payload, raw, _env = licence_format.open_envelope(doc.licence_file or "")
        licence_format.validate_payload(payload)
        _check_site(payload)
        if licence_format.payload_hash(raw) != doc.name:
            raise LicenceError("tampered", "the stored record does not match its signed file")
    except LicenceError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc), "payload": None}
    return {"ok": True, "code": None, "message": None, "payload": payload}


def _compute() -> dict[str, Any]:
    doc = current_doc()
    if doc is None:
        return {"present": False}
    check = verify_stored(doc)
    if not check["ok"]:
        return {"present": True, "valid": False, "number": doc.licence_number, "features": {},
                "reason": check["code"]}
    if doc.status == "Revoked" or doc.revoked_on:
        return {"present": True, "valid": False, "number": doc.licence_number, "features": {}, "reason": "revoked"}
    payload = check["payload"]
    return {"present": True, "valid": True, "number": doc.licence_number, "features": payload["features"],
            "terms": {"expiry_date": payload.get("expiry_date"), "grace_days": payload.get("grace_days") or 0,
                      "licence_type": payload.get("licence_type"), "limits": payload.get("limits") or {}}}


def _data() -> dict[str, Any]:
    data = getattr(frappe.local, "zg_licence_data", None)
    if data is None:
        data = frappe.cache.get_value(CACHE_KEY)
        if data is None:
            data = _compute()
            frappe.cache.set_value(CACHE_KEY, data, expires_in_sec=3600)
        frappe.local.zg_licence_data = data
    return data


def current_entitlement() -> Entitlement:
    """The entitlement of the licence in force. A site with no licence, a licence that no longer verifies, or a
    revoked one gets the foundation only -- never more (Phase 7: deleting the licence record must not lift any
    restriction). Only asked while enforcement is switched on."""
    cached = getattr(frappe.local, "zg_licence_entitlement", None)
    if cached is not None:
        return cached
    data = _data()
    if not data.get("present"):
        ent = Entitlement.from_features({}, source="none")
    else:
        source = f"licence:{data['number']}" if data.get("valid", True) else f"invalid:{data['number']}"
        ent = Entitlement.from_features(data["features"], source=source)
    frappe.local.zg_licence_entitlement = ent
    return ent


def current_terms() -> dict[str, Any] | None:
    """Expiry, grace, type and limits of the valid licence in force (None without one)."""
    data = _data()
    return data.get("terms") if data.get("present") and data.get("valid") else None


def summary(doc=None) -> dict[str, Any]:
    doc = doc or current_doc()
    if doc is None:
        return {"present": False, "site": site_identity.identity()}
    payload = json.loads(doc.payload_json or "{}")
    on = getdate(today())
    state = doc.status if doc.status == "Revoked" else licence_format.status(payload, on) if payload else doc.status
    return {
        "present": True,
        "licence_number": doc.licence_number,
        "licence_id": doc.licence_id,
        "licence_version": doc.licence_version,
        "customer_name": doc.customer_name,
        "edition_id": doc.edition_id,
        "edition_name": doc.edition_name,
        "licence_type": doc.licence_type,
        "status": state,
        "issue_date": str(doc.issue_date or ""),
        "start_date": str(doc.start_date or ""),
        "expiry_date": str(doc.expiry_date) if doc.expiry_date else None,
        "days_remaining": licence_format.days_remaining(payload, on) if payload else None,
        "limits": {"max_users": doc.max_users, "max_companies": doc.max_companies, "max_sites": doc.max_sites},
        "feature_count": doc.feature_count,
        "features": sorted((payload.get("features") or {}).keys()),
        "imported_on": str(doc.imported_on or ""),
        "site": site_identity.identity(),
    }
