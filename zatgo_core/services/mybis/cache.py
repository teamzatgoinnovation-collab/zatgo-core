"""Short-lived cache for MyBis aggregates.

Dashboards are heavy to compute and light to be a minute old, but a financial figure must never look live when it is not:
`cached` returns the payload together with `cached_at` (ISO time it was computed) so the app can show "Updated 2 minutes ago".
The key always carries the user and company: a User Permission can make two users see different numbers for the same
company, so figures are never shared between users.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

import frappe
from frappe.utils import now_datetime

DEFAULT_TTL = 300
PREFIX = "zg_mybis"


def make_key(name: str, company: str, params: dict[str, Any]) -> str:
    digest = hashlib.sha1(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return f"{PREFIX}:{frappe.session.user}:{company}:{name}:{digest}"


def cached(
    name: str,
    company: str,
    params: dict[str, Any],
    compute: Callable[[], Any],
    *,
    ttl: int = DEFAULT_TTL,
    refresh: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """(payload, cache_meta). `refresh` recomputes and overwrites. A cache outage falls through to computing."""
    key = make_key(name, company, params)
    if not refresh:
        try:
            hit = frappe.cache().get_value(key)
        except Exception:
            hit = None
        if hit:
            return hit["payload"], {"cached": True, "cached_at": hit["cached_at"], "ttl": ttl}
    payload = compute()
    stamp = now_datetime().isoformat()
    try:
        frappe.cache().set_value(key, {"payload": payload, "cached_at": stamp}, expires_in_sec=ttl)
    except Exception:
        pass
    return payload, {"cached": False, "cached_at": stamp, "ttl": ttl}
