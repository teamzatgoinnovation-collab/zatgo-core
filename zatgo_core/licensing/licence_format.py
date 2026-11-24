"""The ZatGo licence file: canonical payload, envelope, signature check and payload validation.

File (JSON text, `<number>.zglicence`):

    {"type": "zatgo.licence", "format": 1, "key_id": "<16 hex>",
     "payload": "<base64 of the canonical payload bytes>", "signature": "<base64 Ed25519 signature>"}

The signature covers the exact payload bytes, so verification never depends on re-serialising JSON. The payload
must also *be* canonical (sorted keys, compact separators, UTF-8, no floats): a file whose bytes are not the
canonical form of what they decode to is refused, so two different byte strings can never carry the same
licence.

Payload (schema_version 1):

    licence_id (uuid), licence_number, licence_version (int >= 1; a replacement carries a higher one),
    product_id ("zatgo_erp"), customer_id, customer_name,
    site_ids [site_config zg_site_id values], site_names [optional host names],
    edition_id, edition_name, edition_version,
    features {feature_id: [actions]} (resolved from the edition at issue time; [] = all of the feature),
    modules [module ids, informational],
    licence_type (Trial | Monthly | Yearly | Lifetime | Custom Duration | Perpetual),
    issue_date, start_date, expiry_date (ISO dates; expiry null for Lifetime / Perpetual),
    grace_days, platforms {desk, desktop, mobile}, limits {max_users, max_companies, max_sites} (0 = no limit),
    device_policy, issued_at (ISO datetime, UTC), key_id

A revocation list (`type: "zatgo.revocation"`) is the same envelope around {"revoked": [licence_id, ...],
"issued_at": ..., "product_id": ...}.

Pure Python: the issuer, the importer and the unit tests share it.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Any, Mapping

from zatgo_core.licensing import crypto, edition_config, registry

FILE_TYPE = "zatgo.licence"
REVOCATION_TYPE = "zatgo.revocation"
FORMAT = 1
SCHEMA_VERSION = 1
PRODUCT_ID = edition_config.PRODUCT_ID
NO_EXPIRY_TYPES = ("Lifetime", "Perpetual")
# A licence is a few kilobytes; anything far larger is refused before it is parsed.
MAX_FILE_BYTES = 256 * 1024
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

REQUIRED = (
    "schema_version", "licence_id", "licence_number", "licence_version", "product_id", "customer_name",
    "site_ids", "edition_id", "edition_name", "edition_version", "features", "licence_type", "issue_date",
    "start_date", "expiry_date", "limits", "platforms", "issued_at", "key_id",
)


class LicenceError(Exception):
    """A licence (or revocation) file that must be refused. `code` is stable for the UI and the audit log."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# -- canonical bytes ----------------------------------------------------------------------------------------------

def _no_floats(value: Any, path: str = "payload") -> None:
    if isinstance(value, float):
        raise LicenceError("not_canonical", f"{path} is a decimal number; licences carry whole numbers only")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise LicenceError("not_canonical", f"{path} has a non-text key")
            _no_floats(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _no_floats(v, f"{path}[{i}]")


def canonical(payload: Mapping[str, Any]) -> bytes:
    _no_floats(dict(payload))
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def payload_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# -- envelope -------------------------------------------------------------------------------------------------

def seal(payload: Mapping[str, Any], private_key, kind: str = FILE_TYPE) -> str:
    """Sign a payload and return the file text (issuer side)."""
    kid = crypto.key_id(private_key.public_key())
    body = dict(payload)
    if kind == FILE_TYPE:
        body["key_id"] = kid
    raw = canonical(body)
    envelope = {"type": kind, "format": FORMAT, "key_id": kid, "payload": crypto.b64e(raw),
                "signature": crypto.b64e(crypto.sign(private_key, raw))}
    return json.dumps(envelope, indent=1, sort_keys=True) + "\n"


def open_envelope(text: str | bytes, kind: str = FILE_TYPE) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    """Parse and verify a file. Returns (payload, payload bytes, envelope). Raises LicenceError."""
    if len(text) > MAX_FILE_BYTES:
        raise LicenceError("too_large", "the file is too large to be a ZatGo licence")
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            raise LicenceError("unreadable", "the file is not UTF-8 text") from None
    try:
        envelope = json.loads(text)
    except ValueError:
        raise LicenceError("unreadable", "the file is not a ZatGo licence (not JSON)") from None
    if not isinstance(envelope, dict):
        raise LicenceError("unreadable", "the file is not a ZatGo licence")
    ftype = envelope.get("type")
    if ftype == edition_config.FILE_TYPE:
        raise LicenceError("wrong_type", "this is an edition configuration, not a licence")
    if ftype != kind:
        raise LicenceError("wrong_type", f"expected a {kind} file, got {ftype!r}")
    if envelope.get("format") != FORMAT:
        raise LicenceError("unsupported_format", f"unsupported licence file format {envelope.get('format')!r}")
    kid = envelope.get("key_id")
    try:
        raw = crypto.b64d(envelope.get("payload") or "")
        signature = crypto.b64d(envelope.get("signature") or "")
    except (ValueError, TypeError):
        raise LicenceError("unreadable", "the payload or signature is not valid base64") from None
    try:
        good = crypto.verify(str(kid or ""), raw, signature)
    except crypto.KeyError_ as exc:
        raise LicenceError("unknown_key", str(exc)) from None
    if not good:
        raise LicenceError("bad_signature", "the signature does not match: the file was changed or not issued by ZatGo")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise LicenceError("unreadable", "the signed payload is not JSON") from None
    if not isinstance(payload, dict):
        raise LicenceError("unreadable", "the signed payload is not an object")
    if canonical(payload) != raw:
        raise LicenceError("not_canonical", "the signed payload is not in canonical form")
    if kind == FILE_TYPE and payload.get("key_id") != kid:
        raise LicenceError("bad_signature", "the payload names a different signing key than the envelope")
    return payload, raw, envelope


# -- payload validation -------------------------------------------------------------------------------------

def _date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise LicenceError("invalid", f"{field} is not a date (YYYY-MM-DD)") from None


def validate_payload(payload: Mapping[str, Any]) -> None:
    """Shape, product, dates and features of a payload. Site and time checks are the importer's."""
    missing = [k for k in REQUIRED if k not in payload]
    if missing:
        raise LicenceError("invalid", f"the licence lacks {', '.join(missing)}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise LicenceError("unsupported_schema",
                           f"licence schema {payload['schema_version']!r} needs a newer ZatGo version (this one reads {SCHEMA_VERSION})")
    if payload["product_id"] != PRODUCT_ID:
        raise LicenceError("wrong_product", f"the licence is for product {payload['product_id']!r}, not ZatGo ERP")
    if not UUID_RE.match(str(payload["licence_id"])):
        raise LicenceError("invalid", "licence_id is not a UUID")
    if not isinstance(payload["licence_version"], int) or payload["licence_version"] < 1:
        raise LicenceError("invalid", "licence_version must be a whole number >= 1")
    if payload["licence_type"] not in edition_config.LICENCE_TYPES:
        raise LicenceError("invalid", f"unknown licence type {payload['licence_type']!r}")
    sites = payload["site_ids"]
    if not isinstance(sites, list) or not sites or not all(isinstance(s, str) and s for s in sites):
        raise LicenceError("invalid", "the licence names no site")
    issue, start = _date(payload["issue_date"], "issue_date"), _date(payload["start_date"], "start_date")
    if start < issue:
        raise LicenceError("invalid_dates", "the licence starts before it was issued")
    expiry = payload["expiry_date"]
    if payload["licence_type"] in NO_EXPIRY_TYPES:
        if expiry is not None:
            raise LicenceError("invalid_dates", f"a {payload['licence_type']} licence has no expiry date")
    else:
        if expiry is None:
            raise LicenceError("invalid_dates", f"a {payload['licence_type']} licence needs an expiry date")
        if _date(expiry, "expiry_date") < start:
            raise LicenceError("invalid_dates", "the licence expires before it starts")
    limits = payload["limits"]
    if not isinstance(limits, dict) or any(not isinstance(limits.get(k, 0), int) or limits.get(k, 0) < 0
                                            for k in ("max_users", "max_companies", "max_sites")):
        raise LicenceError("invalid", "limits must be whole numbers >= 0")
    if limits.get("max_sites") and len(sites) > limits["max_sites"]:
        raise LicenceError("invalid", "the licence names more sites than it allows")
    features = payload["features"]
    if not isinstance(features, dict):
        raise LicenceError("invalid", "features must be a map")
    unknown = sorted(f for f in features if registry.get_feature(f) is None)
    if unknown:
        raise LicenceError("unknown_features",
                           f"the licence grants features this ZatGo version does not know ({', '.join(unknown[:5])}): update zatgo_core first")
    problems = [p for p in edition_config.feature_problems(features) if "retired" not in p]
    if problems:
        raise LicenceError("invalid_features", "; ".join(problems[:5]))


def validate_revocation(payload: Mapping[str, Any]) -> list[str]:
    if payload.get("product_id") != PRODUCT_ID:
        raise LicenceError("wrong_product", "the revocation list is not for ZatGo ERP")
    revoked = payload.get("revoked")
    if not isinstance(revoked, list) or not all(isinstance(r, str) and UUID_RE.match(r) for r in revoked):
        raise LicenceError("invalid", "the revocation list is malformed")
    return list(revoked)


def status(payload: Mapping[str, Any], today: date, warn_days: int = 30) -> str:
    """Trial / Active / Expiring / Expired / Scheduled for a valid payload at `today` (Suspended, Revoked and
    Invalid are set by the site, not derived from dates)."""
    start = _date(payload["start_date"], "start_date")
    if today < start:
        return "Scheduled"
    expiry = payload.get("expiry_date")
    if expiry is None:
        return "Active"
    end = _date(expiry, "expiry_date")
    if today > end:
        return "Expired"
    if payload["licence_type"] == "Trial":
        return "Trial"
    if (end - today).days <= warn_days:
        return "Expiring"
    return "Active"


def days_remaining(payload: Mapping[str, Any], today: date) -> int | None:
    expiry = payload.get("expiry_date")
    if expiry is None:
        return None
    return max(0, (_date(expiry, "expiry_date") - today).days)
