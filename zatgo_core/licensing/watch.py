"""Audit licensing configuration that lives outside the database (brief Part 17: "site identity changed").

The enforcement switch, issuer mode, the signing-key path and the site ID are `site_config.json` keys a bench user
edits by hand -- no document event sees that. `check()` compares them with what it saw last (DefaultValue row
`zg_licence_config_seen`, written directly like the clock mark) and writes one Audit Log entry per change
(`doctype_name` "Licence Config"). It runs daily (services/jobs.py) and whenever the Licence page loads.
Values are recorded, except the key path, which is recorded only as set / not set.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

SEEN_KEY = "zg_licence_config_seen"
AUDIT_DOCTYPE = "Licence Config"


def snapshot() -> dict[str, Any]:
    from zatgo_core.licensing import entitlement, issuer, issuing, licence_policy, site_identity

    return {
        "enforcement": int(entitlement.enforcement_switch()),
        "issuer": int(issuer.is_issuer_site()),
        "issuer_key_configured": int(bool(frappe.conf.get(issuing.KEY_CONF))),
        "site_id": site_identity.site_id() or None,
        "clock_tolerance_hours": licence_policy.tolerance_hours(),
    }


def _stored() -> dict[str, Any] | None:
    raw = frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": SEEN_KEY}, "defvalue")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _store(value: dict[str, Any]) -> None:
    text = json.dumps(value, sort_keys=True)
    name = frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": SEEN_KEY}, "name")
    if name:
        frappe.db.set_value("DefaultValue", name, "defvalue", text, update_modified=False)
    else:
        frappe.get_doc({"doctype": "DefaultValue", "parent": "__default", "parenttype": "__default",
                        "parentfield": "system_defaults", "defkey": SEEN_KEY, "defvalue": text}).db_insert()


def check() -> list[str]:
    """Audit what changed since the last check; returns the changed keys. The first run only records."""
    from zatgo_core.licensing import audit

    now = snapshot()
    before = _stored()
    if before == now:
        return []
    changed = sorted(k for k in now if before is not None and before.get(k) != now.get(k))
    for key in changed:
        audit.log("licence_config_changed", AUDIT_DOCTYPE, key, {"key": key, "from": before.get(key), "to": now[key]},
                  reason="site_config changed outside ZatGo")
    _store(now)
    return changed


def daily() -> None:
    try:
        check()
    except Exception:
        frappe.log_error(title="ZatGo licence config check failed")
