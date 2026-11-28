"""Every whitelisted zatgo_core API endpoint has a licensing decision (Phase 9, brief Part 5 "RPC methods").

An endpoint is either
- **owned by a feature** (registry `api_prefixes`), an **app** (services/app_catalog.py) or an **industry**
  (industries/registry.py) -- an app or industry the licence leaves out answers 404 like a switched-off one; or
- listed in `NOT_LICENSED` below with the reason it is not product-controlled.

Either way, the documents an endpoint writes still pass the document-level licence gate (licensing/gate.py), so
an endpoint cannot be used to create something the licence does not include. `tests/integration/
test_licensing_api_coverage.py` fails when a new endpoint has no decision, or an entry here no longer matches.
"""

from __future__ import annotations

API_ROOT = "zatgo_core.api.v1."

# prefix -> why it is not licensed per feature. Prefixes end with "." (module paths).
NOT_LICENSED: dict[str, str] = {
    # platform: must work on every site whatever its licence
    "zatgo_core.api.v1.health.": "platform health check (no data)",
    "zatgo_core.api.v1.modules.": "module state for clients (read-only, no business data)",
    "zatgo_core.api.v1.accounting.health.": "platform health check (no data)",
    "zatgo_core.api.v1.admin.health.": "platform health check (no data)",
    "zatgo_core.api.v1.crm.health.": "platform health check (no data)",
    "zatgo_core.api.v1.customer_portal.health.": "platform health check (no data)",
    "zatgo_core.api.v1.delivery.health.": "platform health check (no data)",
    "zatgo_core.api.v1.documentation.health.": "platform health check (no data)",
    "zatgo_core.api.v1.fleet.health.": "platform health check (no data)",
    "zatgo_core.api.v1.vendor_portal.health.": "platform health check (no data)",
    "zatgo_core.api.v1.warehouse.health.": "platform health check (no data)",
    "zatgo_core.api.v1.licensing.": "licensing itself: must work in every licence state (import, renew, verify)",
    "zatgo_core.api.v1.subscription.": "the Space subscription (its own gate)",
    "zatgo_core.api.v1.admin.overview.": "platform administration (System Manager)",
    "zatgo_core.api.v1.app_hub.": "switching apps on/off (refuses an unlicensed app itself: app_authority)",
    "zatgo_core.api.v1.apps.": "client app registry (platform administration)",
    "zatgo_core.api.v1.config.": "ZatGo settings (platform administration)",
    "zatgo_core.api.v1.settings.": "ZatGo settings (platform administration)",
    "zatgo_core.api.v1.features.": "rollout feature flags (not licensing)",
    "zatgo_core.api.v1.integrations.": "integration settings (platform administration)",
    "zatgo_core.api.v1.devices.": "a user's own push tokens",
    "zatgo_core.api.v1.language.": "the user's language",
    "zatgo_core.api.v1.documentation.meta.": "API documentation (no data)",
    "zatgo_core.api.v1.erp_summary.": "Desk summary of the user's own permitted data (reads only)",
    "zatgo_core.api.v1.sync.batch.": "client batch sync: every document it writes passes the document gate",
    # portals: website users of a customer / supplier, not licensed seats
    "zatgo_core.api.v1.customer_portal.": "customer portal (website users; reads their own orders)",
    "zatgo_core.api.v1.vendor_portal.": "supplier portal (website users; reads their own purchase orders)",
    # products not in the registry yet: register them before selling them
    "zatgo_core.api.v1.delivery.": "delivery product -- not in the licensing registry yet",
    "zatgo_core.api.v1.fleet.": "fleet product -- not in the licensing registry yet",
    # present on the dev bench only, not in the repository
    "zatgo_core.api.v1.settings_map.": "settings map page (dev bench only)",
}

# Exemptions for code that may be absent from a checkout (the stale-entry test skips them).
OPTIONAL = frozenset({"zatgo_core.api.v1.settings_map."})


def owners() -> list[tuple[str, str]]:
    """(prefix, owner) for every licensed prefix: feature ids, `app:<key>`, `industry:<key>`."""
    from zatgo_core.industries import registry as industries
    from zatgo_core.licensing import registry
    from zatgo_core.services import app_catalog

    out = [(p, f.id) for f in registry.features() if not f.retired for p in f.api_prefixes]
    out += [(p, f"app:{key}") for key, prefixes in app_catalog.api_prefixes().items() for p in prefixes]
    out += [(p, f"industry:{i.key}") for i in industries.INDUSTRIES.values() for p in i.api_prefixes]
    return out


def classify(method: str) -> dict[str, str] | None:
    """{"kind": "licensed" | "not_licensed", "owner" | "reason"} for a dotted method path; None = no decision."""
    target = method if method.endswith(".") else method + "."
    licensed = [owner for prefix, owner in owners() if target.startswith(prefix)]
    if licensed:
        return {"kind": "licensed", "owner": ", ".join(sorted(set(licensed)))}
    for prefix, reason in NOT_LICENSED.items():
        if target.startswith(prefix):
            return {"kind": "not_licensed", "reason": reason}
    return None
