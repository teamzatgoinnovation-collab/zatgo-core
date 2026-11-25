"""Issuing licences on the ZatGo licence issuer site (decision D2; brief Part 8 "licence generation").

1. take an **Active** edition and resolve its features (with narrowed actions) at this moment;
2. build the canonical payload (customer, sites, dates, limits, platforms) and validate it;
3. give it a new licence id -- or, for a replacement, the same id with the next `licence_version`;
4. sign it with the issuer's Ed25519 key (`site_config` `zg_licence_issuer_key` = path to a PEM file outside the
   bench's `sites/` folder, owner-readable only);
5. record it in `Licence History` (the file, never the key) and return the file text.

The signing key must be one this app version trusts (`licensing/keys/public_keys.json`), or customers could
not verify the licence: issuing with any other key is refused.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from typing import Any, Iterable, Mapping

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import getdate, now_datetime, nowdate

from zatgo_core.licensing import audit, crypto, editions, issuer, licence_format, registry
from zatgo_core.licensing.licence_format import LicenceError
from zatgo_core.licensing.licences import _write

HISTORY = "Licence History"
KEY_CONF = "zg_licence_issuer_key"
NUMBER_SERIES = "ZGL-.YYYY.-.#####"


def signing_key():
    issuer.require_issuer_manager()
    path = frappe.conf.get(KEY_CONF)
    if not path:
        frappe.throw(_("No licence signing key is configured on this issuer site ({0} in site_config).").format(KEY_CONF))
    sites_dir = os.path.abspath(frappe.get_site_path(".."))
    try:
        key = crypto.load_private_key(path, sites_dir=sites_dir)
    except (crypto.KeyError_, OSError, ValueError) as exc:
        frappe.throw(_("The licence signing key cannot be used: {0}").format(str(exc)))
    kid = crypto.key_id(key.public_key())
    if kid not in crypto.trusted_keys():
        frappe.throw(_("Signing key {0} is not in licensing/keys/public_keys.json: customers could not verify "
                       "its licences. Add it there and deploy first.").format(kid))
    return key


def _expiry(licence_type: str, start: date, duration_days: int, explicit: Any) -> str | None:
    if licence_type in licence_format.NO_EXPIRY_TYPES:
        return None
    if explicit:
        return str(getdate(explicit))
    if licence_type == "Monthly":
        duration_days = duration_days or 30
    if not duration_days:
        frappe.throw(_("A {0} licence needs an expiry date or a duration.").format(licence_type))
    return str(start + timedelta(days=int(duration_days) - 1))


def issue(
    edition_id: str,
    customer_name: str,
    site_ids: Iterable[str],
    *,
    customer_id: str = "",
    site_names: Iterable[str] = (),
    licence_type: str | None = None,
    start_date: Any = None,
    expiry_date: Any = None,
    duration_days: int | None = None,
    limits: Mapping[str, int] | None = None,
    grace_days: int = 0,
    device_policy: str = "none",
    replaces: str | None = None,
) -> dict[str, Any]:
    """Sign a licence for an Active edition. `replaces` = a licence id this one supersedes (same id, next
    version). Returns {"licence_number", "licence_id", "licence_version", "filename", "file"}."""
    key = signing_key()
    config = editions.get_config(edition_id)
    if config["status"] != "Active":
        frappe.throw(_("Only an Active edition can be licensed; {0} is {1}.").format(edition_id, config["status"]))
    if not editions.inspect(config["features"], config["platforms"])["ok"]:
        frappe.throw(_("Edition {0} misses dependencies; fix it before licensing.").format(edition_id))

    lic_defaults = config["licence_defaults"]
    ltype = licence_type or lic_defaults["licence_type"]
    start = getdate(start_date or nowdate())
    duration = duration_days if duration_days is not None else (
        lic_defaults["trial_days"] if ltype == "Trial" else lic_defaults["duration_days"])
    limits = {"max_users": lic_defaults["max_users"], "max_companies": lic_defaults["max_companies"],
              "max_sites": 1, **(limits or {})}
    sites = [s.strip() for s in site_ids if s and s.strip()]

    if replaces:
        versions = frappe.get_all(HISTORY, filters={"licence_id": replaces}, pluck="licence_version")
        if not versions:
            frappe.throw(_("No issued licence has id {0}.").format(replaces))
        licence_id, version = replaces, max(int(v or 0) for v in versions) + 1
    else:
        licence_id, version = str(uuid.uuid4()), 1

    payload = {
        "schema_version": licence_format.SCHEMA_VERSION,
        "licence_id": licence_id,
        "licence_number": make_autoname(NUMBER_SERIES),
        "licence_version": version,
        "product_id": licence_format.PRODUCT_ID,
        "customer_id": customer_id or "",
        "customer_name": customer_name,
        "site_ids": sites,
        "site_names": [s.strip() for s in site_names if s and s.strip()],
        "edition_id": config["edition_id"],
        "edition_name": config["edition_name"],
        "edition_version": config["version"],
        "features": config["features"],
        "modules": sorted({registry.get_feature(f).module for f in config["features"] if registry.get_feature(f)}),
        "licence_type": ltype,
        "issue_date": nowdate(),
        "start_date": str(start),
        "expiry_date": _expiry(ltype, start, duration, expiry_date),
        "grace_days": int(grace_days or 0),
        "platforms": config["platforms"],
        "limits": {k: int(v or 0) for k, v in limits.items()},
        "device_policy": device_policy,
        "issued_at": now_datetime().strftime("%Y-%m-%dT%H:%M:%S"),
        "key_id": crypto.key_id(key.public_key()),
    }
    try:
        licence_format.validate_payload(payload)
    except LicenceError as exc:
        frappe.throw(_("Cannot issue: {0}").format(str(exc)))
    text = licence_format.seal(payload, key)
    raw = licence_format.canonical(payload)
    _write(_record, payload, text, licence_format.payload_hash(raw))
    audit.log("licence_issued", HISTORY, payload["licence_number"],
              {"licence_id": licence_id, "version": version, "edition": edition_id, "customer": customer_name,
               "sites": len(sites), "key_id": payload["key_id"]})
    return {"licence_number": payload["licence_number"], "licence_id": licence_id, "licence_version": version,
            "filename": f"{payload['licence_number']}.zglicence", "file": text}


def _record(payload: Mapping[str, Any], text: str, digest: str) -> None:
    frappe.get_doc({
        "doctype": HISTORY,
        "licence_number": payload["licence_number"],
        "licence_id": payload["licence_id"],
        "licence_version": payload["licence_version"],
        "customer_id": payload["customer_id"],
        "customer_name": payload["customer_name"],
        "edition_id": payload["edition_id"],
        "edition_version": payload["edition_version"],
        "licence_type": payload["licence_type"],
        "issue_date": payload["issue_date"],
        "start_date": payload["start_date"],
        "expiry_date": payload["expiry_date"],
        "site_ids": "\n".join(payload["site_ids"]),
        "site_names": "\n".join(payload["site_names"]),
        "issued_by": frappe.session.user,
        "issued_on": now_datetime(),
        "key_id": payload["key_id"],
        "payload_hash": digest,
        "licence_file": text,
    }).insert(ignore_permissions=True)


def revocation_list(licence_ids: Iterable[str]) -> dict[str, Any]:
    """Sign a revocation list for licences this issuer issued; marks them revoked in the history."""
    key = signing_key()
    ids = sorted({i.strip() for i in licence_ids if i and i.strip()})
    known = set(frappe.get_all(HISTORY, filters={"licence_id": ["in", ids or ["-"]]}, pluck="licence_id"))
    if unknown := [i for i in ids if i not in known]:
        frappe.throw(_("Not issued here: {0}").format(", ".join(unknown)))
    payload = {"product_id": licence_format.PRODUCT_ID, "revoked": ids,
               "issued_at": now_datetime().strftime("%Y-%m-%dT%H:%M:%S")}
    text = licence_format.seal(payload, key, kind=licence_format.REVOCATION_TYPE)

    def _mark():
        for name in frappe.get_all(HISTORY, filters={"licence_id": ["in", ids]}, pluck="name"):
            frappe.db.set_value(HISTORY, name, "revoked_on", now_datetime(), update_modified=False)

    _write(_mark)
    audit.log("revocation_issued", HISTORY, None, {"licence_ids": ids})
    return {"revoked": ids, "filename": f"revocation-{nowdate()}.zgrevocation", "file": text}


def history(limit: int = 100) -> list[dict[str, Any]]:
    issuer.require_issuer_manager()
    return frappe.get_all(HISTORY, fields=["licence_number", "licence_id", "licence_version", "customer_name",
                                           "edition_id", "licence_type", "start_date", "expiry_date", "issued_on",
                                           "revoked_on"], order_by="creation desc", limit_page_length=limit)

