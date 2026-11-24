"""What the Licence page shows (brief Part 9): overview, module access, warnings, history, exports.

Read-only views over `licences.py` (the licence in force, re-verified), the registry and this site's own
counts. Nothing here writes, except `site_identity(create=True)` the first time the site ID is asked for.

Counting (decision D9): licensed users = enabled System Users other than Administrator; companies = Company
records. Limits are shown and warned about here; refusing new users / companies over the limit is Phase 7.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import now_datetime, today

from zatgo_core.licensing import crypto, edition_config, entitlement, licences, registry
from zatgo_core.licensing import site_identity

TRIAL_WARN_DAYS = 7
EXPIRY_WARN_DAYS = 30


def active_users() -> int:
    return frappe.db.count("User", {"enabled": 1, "user_type": "System User",
                                    "name": ["not in", ["Administrator", "Guest"]]})


def companies() -> int:
    return frappe.db.count("Company")


def _payload(doc) -> dict[str, Any]:
    try:
        return json.loads(doc.payload_json or "{}")
    except ValueError:
        return {}


def module_access(features: dict[str, list[str]] | None) -> list[dict[str, Any]]:
    """Per module: its features and whether the licence includes them (None = no licence: nothing restricted)."""
    out = []
    for module in registry.modules():
        rows = []
        for f in registry.features_of_module(module.id):
            if f.retired:
                continue
            if f.foundation:
                licensed, actions = True, list(edition_config.feature_actions(f))
            elif features is None:
                licensed, actions = None, list(edition_config.feature_actions(f))
            else:
                licensed = f.id in features
                actions = list(edition_config.effective_actions(f, features.get(f.id) or ())) if licensed else []
            rows.append({"id": f.id, "label": f.label, "licensed": licensed, "actions": actions,
                         "source_app": f.source_app})
        if rows:
            on = sum(1 for r in rows if r["licensed"])
            out.append({"id": module.id, "label": module.label, "category": module.category, "features": rows,
                        "licensed": on, "total": len(rows)})
    return out


def warnings(summary: dict[str, Any], check: dict[str, Any] | None, enforcement: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []

    def add(level: str, code: str, text: str) -> None:
        out.append({"level": level, "code": code, "message": text})

    if not crypto.shipped_keys():
        add("info", "no_trusted_keys",
            "This ZatGo version trusts no licence signing key yet, so no licence can be imported. "
            "The key is added when licensing goes live (docs/licensing.md, Keys).")
    if not summary.get("present"):
        if enforcement["switch"]:
            add("danger", "no_licence", "Licence enforcement is switched on for this site but no licence is "
                                        "imported. Import the licence ZatGo issued for this site.")
        else:
            add("info", "no_licence", "No licence is imported on this site. Nothing is restricted.")
        return out
    if check and not check["ok"]:
        add("danger", f"invalid_{check['code']}",
            f"The licence in force no longer verifies ({check['message']}). Only the basics stay available "
            "while licensing is enforced. Import a valid licence.")
    status = summary["status"]
    days = summary.get("days_remaining")
    if status == "Revoked":
        add("danger", "revoked", "This licence was revoked by ZatGo. Import a replacement licence.")
    elif status == "Expired":
        add("danger", "expired", f"This licence expired on {summary['expiry_date']}.")
    elif status == "Trial" and days is not None and days <= TRIAL_WARN_DAYS:
        add("warning", "trial_ending", f"The trial ends in {days} day(s), on {summary['expiry_date']}.")
    elif status in ("Expiring", "Trial", "Active") and days is not None and days <= EXPIRY_WARN_DAYS:
        add("warning", "expiring", f"This licence expires in {days} day(s), on {summary['expiry_date']}.")
    limits = summary.get("limits") or {}
    users, comps = summary["usage"]["users"], summary["usage"]["companies"]
    if limits.get("max_users") and users > limits["max_users"]:
        add("warning", "users_exceeded", f"{users} active users; the licence allows {limits['max_users']}.")
    if limits.get("max_companies") and comps > limits["max_companies"]:
        add("warning", "companies_exceeded", f"{comps} companies; the licence allows {limits['max_companies']}.")
    if not enforcement["switch"]:
        add("info", "not_enforced", "The licence is imported but not enforced on this site (enforcement switch off).")
    return out


def history(limit: int = 50) -> dict[str, list[dict[str, Any]]]:
    rows = frappe.get_all(licences.DOCTYPE, fields=[
        "name", "licence_number", "licence_version", "edition_name", "licence_type", "status", "is_current",
        "start_date", "expiry_date", "imported_on", "imported_by", "revoked_on"], order_by="imported_on desc",
        limit_page_length=limit)
    events = frappe.get_all("ZG Audit Log", filters={"doctype_name": licences.DOCTYPE}, fields=[
        "fieldname", "document_name", "new_value", "reason", "changed_by", "creation"],
        order_by="creation desc", limit_page_length=limit)
    for e in events:
        e["event"] = e.pop("fieldname")
    return {"licences": rows, "events": events}


def overview() -> dict[str, Any]:
    summary = licences.summary()
    doc = licences.current_doc()
    check = licences.verify_stored(doc) if doc else None
    payload = _payload(doc) if doc else {}
    enforcement = entitlement.describe()
    summary["usage"] = {"users": active_users(), "companies": companies()}
    if doc:
        summary["product_id"] = payload.get("product_id")
        summary["platforms"] = payload.get("platforms")
        summary["verified"] = bool(check and check["ok"])
        summary["verified_on"] = str(doc.verified_on or "")
    features = (payload.get("features") or {}) if doc and check and check["ok"] and summary["status"] != "Revoked" \
        else ({} if doc else None)
    return {
        "licence": summary,
        "modules": module_access(features),
        "warnings": warnings(summary, check, enforcement),
        "enforcement": enforcement,
        "site": site_identity.identity(),
        "trusted_keys": sorted(crypto.shipped_keys()),
        "today": today(),
    }


def site_request() -> dict[str, Any]:
    """The file a customer sends ZatGo to get a licence for this site."""
    ident = site_identity.identity(create=True)
    return {"type": "zatgo.site_request", "format": 1, **ident, "site_url": frappe.utils.get_url(),
            "usage": {"users": active_users(), "companies": companies()}, "generated_at": str(now_datetime())}


def licence_info() -> dict[str, Any]:
    """Licence metadata backup / export: everything shown, plus the history. Not a licence, never importable."""
    data = overview()
    return {"type": "zatgo.licence_info", "format": 1, "generated_at": str(now_datetime()),
            "licence": data["licence"], "modules": data["modules"], "warnings": data["warnings"],
            "site": data["site"], "history": history(200)}


def licence_file(name: str) -> dict[str, str]:
    doc = frappe.get_doc(licences.DOCTYPE, name)
    return {"filename": f"{doc.licence_number}.zglicence", "file": doc.licence_file or ""}

