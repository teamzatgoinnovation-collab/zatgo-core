"""The capability contract for ZatGo's own clients: VanSaleX (mobile / web), ZatGo POS and the desktop accounting
apps, MyBis (Phase 8, docs/licensing.md "Client contract").

One payload, same stable ids as the registry and the licence, so a client can hide what this site is not licensed
for instead of letting the user hit a refusal. It is a **hint**: every rule is enforced on the server whatever a
client shows (licensing/gate.py, services/subscription_gate.py, the app and industry gates). A hidden mobile
feature is not a secure one.

Kept apart, as the brief asks: what the **licence** gives (`features`, `modules`, `platforms`), what the site has
**switched on** (`apps`, `industries`), and what the **user's roles** allow -- clients keep asking Frappe for
document permissions; `user.roles` is only for display.

Shape (schema_version 1):

    {"schema_version": 1, "product_id": "zatgo_erp", "digest": "<16 hex: changes when anything below changes>",
     "licence": {enforced, licensed, read_only, read_only_reason, message, edition_id, edition_name, status,
                 expiry_date, days_remaining},
     "platforms": {"desk": 1, "desktop": 0|1, "mobile": 0|1}, "platform": "<asked>", "platform_allowed": bool,
     "modules": {module_id: true | false | null}, "features": {feature_id: {"licensed": true|false|null,
                 "actions": [...]}}, "apps": {app_key: bool}, "industries": [...],
     "user": {"name", "roles"}}

`null` (licensed) = the site enforces no licence: nothing is restricted by licensing.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe

from zatgo_core.licensing import edition_config, entitlement, licences, registry

SCHEMA_VERSION = 1
PLATFORMS = registry.PLATFORMS


def safe_licence_block() -> dict[str, Any]:
    """licence_block() for payloads that must never fail (login contexts): an error is logged, not raised."""
    try:
        return licence_block()
    except Exception:
        frappe.log_error(title="ZatGo licence block failed")
        return {"enforced": False, "licensed": False, "read_only": False, "read_only_reason": None,
                "message": None, "edition_id": None, "edition_name": None, "status": None, "expiry_date": None,
                "days_remaining": None, "error": True}


def licence_block() -> dict[str, Any]:
    """The compact block VanSaleX `me`, POS settings and MyBis context carry."""
    from zatgo_core.services import subscription_gate

    ent = entitlement.active()
    gate_state = subscription_gate.current()
    lic_ro = (gate_state.get("licence") or {}) if gate_state.get("read_only") else {}
    summary = licences.summary() if ent is not None else {"present": False}
    return {
        "enforced": ent is not None,
        "licensed": bool(ent and ent.source.startswith("licence:")),
        "read_only": bool(gate_state.get("read_only")),
        "read_only_reason": gate_state.get("reason") if gate_state.get("read_only") else None,
        "message": subscription_gate.read_only_message() if gate_state.get("read_only") else None,
        "edition_id": summary.get("edition_id"),
        "edition_name": summary.get("edition_name"),
        "status": summary.get("status"),
        "expiry_date": summary.get("expiry_date") or (lic_ro.get("expiry_date") if lic_ro else None),
        "days_remaining": summary.get("days_remaining"),
    }


def _platforms(ent) -> dict[str, int]:
    """The licence's platforms; every platform when no valid licence is enforced (nothing to narrow)."""
    terms = licences.current_terms() if ent is not None else None
    allowed = (terms or {}).get("platforms")
    if not allowed:
        return {p: 1 for p in PLATFORMS}
    return {p: int(bool(allowed.get(p))) for p in PLATFORMS}


def for_user(platform: str | None = None) -> dict[str, Any]:
    from zatgo_core.industries.gate import enabled_keys
    from zatgo_core.services import app_state

    ent = entitlement.active()
    features: dict[str, Any] = {}
    modules: dict[str, Any] = {}
    for module in registry.modules():
        live = [f for f in registry.features_of_module(module.id) if not f.retired]
        if not live:
            continue
        flags = []
        for f in live:
            if ent is None:
                licensed, actions = None, list(edition_config.feature_actions(f))
            else:
                licensed = f.id in ent.features
                actions = list(ent.features[f.id]) if licensed else []
            features[f.id] = {"licensed": licensed, "actions": actions}
            flags.append(licensed)
        modules[module.id] = None if ent is None else any(flags)
    platforms = _platforms(ent)
    asked = (platform or "").strip().lower() or None
    payload = {
        "schema_version": SCHEMA_VERSION,
        "product_id": edition_config.PRODUCT_ID,
        "licence": licence_block(),
        "platforms": platforms,
        "platform": asked,
        "platform_allowed": True if asked is None or asked not in platforms else bool(platforms[asked]),
        "modules": modules,
        "features": features,
        "apps": app_state.switches(),
        "industries": sorted(enabled_keys()),
        "user": {"name": frappe.session.user, "roles": sorted(frappe.get_roles())},
    }
    body = {k: v for k, v in payload.items() if k != "user"}
    payload["digest"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return payload
