"""Shared plumbing of the MyBis endpoints: scope, guard, cache, envelope."""

from __future__ import annotations

from typing import Any

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_login
from zatgo_core.services.mybis import cache, queries, scope

PERIOD_ARGS = ("company", "preset", "from_date", "to_date", "compare")


def run(name: str, args: dict[str, Any], kinds: tuple[str, ...], build, refresh: Any, ttl: int = cache.DEFAULT_TTL) -> dict[str, Any]:
    require_login()
    s = scope.resolve_scope(args.get("company"), args.get("preset"), args.get("from_date"), args.get("to_date"), args.get("compare", 1))
    queries.guard(*kinds)
    key_params = {**s.meta(), **{k: v for k, v in args.items() if k not in ("company", "preset", "from_date", "to_date", "compare")}}
    payload, meta = cache.cached(name, s.company, key_params, lambda: build(s), ttl=ttl, refresh=str(refresh).lower() in ("1", "true", "yes"))
    return ok(payload, meta={**s.meta(), **meta})
