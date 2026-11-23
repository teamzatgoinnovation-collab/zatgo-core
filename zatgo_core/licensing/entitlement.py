"""Entitlement: what this site is licensed for, compiled for fast permission checks (docs/licensing.md).

An entitlement is a set of registry features, each with the actions it may use (the foundation is always in).
It is built from a *verified* source only. Phase 4 ships the model and the enforcement; the source -- a signed
licence verified on import -- arrives in Phase 5. Until then no site has an entitlement, so nothing is enforced
anywhere.

Enforcement is on only when BOTH hold:
- `site_config.json` has `"zg_licence_enforcement": 1` (a file only the bench user writes -- decision D4), and
- an entitlement exists for the site.
Anything else is unrestricted (fail-open), so an unmanaged or not-yet-licensed site is never locked out.

`use(entitlement)` installs one for the current request / test (`frappe.local`): Phase 5's licence loader and
the tests go through it. It is Python-only -- nothing reachable over HTTP sets it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import frappe
from frappe.utils import cint

from zatgo_core.licensing import edition_config, registry

CONF_KEY = "zg_licence_enforcement"
_LOCAL_KEY = "zg_entitlement"


@dataclass(frozen=True)
class Entitlement:
    features: Mapping[str, tuple[str, ...]]  # feature id -> effective actions (foundation included)
    source: str = ""
    # derived
    feature_ids: frozenset[str] = field(default=frozenset())
    app_keys: frozenset[str] = field(default=frozenset())
    industries: frozenset[str] = field(default=frozenset())
    vansalex_keys: frozenset[str] = field(default=frozenset())
    workspaces: frozenset[str] = field(default=frozenset())
    pages: frozenset[str] = field(default=frozenset())
    digest: str = ""

    @classmethod
    def from_features(cls, features: Mapping[str, Iterable[str]] | Iterable[str], source: str = "") -> "Entitlement":
        """From an edition-style map {feature_id: [actions]} ([] = all of the feature). Unknown and retired ids
        are dropped (a licence may name a feature a later app version retired); the foundation is added."""
        chosen: dict[str, tuple[str, ...]] = {}
        for fid, narrowed in edition_config.normalise_features(features).items():
            feature = registry.get_feature(fid)
            if feature is None or feature.retired:
                continue
            chosen[fid] = tuple(edition_config.effective_actions(feature, narrowed))
        for feature in registry.foundation_features():
            chosen[feature.id] = edition_config.feature_actions(feature)
        live = [registry.get_feature(fid) for fid in chosen]
        digest = hashlib.sha256(json.dumps(chosen, sort_keys=True).encode()).hexdigest()[:16]
        return cls(
            features=chosen,
            source=source,
            feature_ids=frozenset(chosen),
            app_keys=frozenset(f.app_key for f in live if f.app_key),
            industries=frozenset(f.industry for f in live if f.industry),
            vansalex_keys=frozenset(k for f in live for k in f.vansalex_keys),
            workspaces=frozenset(w for f in live for w in f.workspaces),
            pages=frozenset(p for f in live for p in f.pages),
            digest=digest,
        )

    def grants(self, doctype: str) -> list[tuple[str, registry.DocTypeGrant, frozenset[str]]]:
        """(feature id, grant, licensed actions) for every licensed grant on this DocType."""
        out = []
        for fid, grant in registry.doctype_index().get(doctype, ()):
            if fid in self.features:
                acts = frozenset(a for a in grant.actions if a in self.features[fid])
                out.append((fid, grant, acts))
        return out


def enforcement_switch() -> bool:
    return cint(frappe.conf.get(CONF_KEY)) == 1


def use(entitlement: Entitlement | None) -> None:
    """Install (or clear, with None) the entitlement for this request / test."""
    setattr(frappe.local, _LOCAL_KEY, entitlement)


def _load() -> Entitlement | None:
    """The verified source. Phase 4 has none: the signed-licence loader (Phase 5) plugs in here."""
    return None


def current() -> Entitlement | None:
    installed = getattr(frappe.local, _LOCAL_KEY, None)
    if installed is not None:
        return installed
    return _load()


def active() -> Entitlement | None:
    """The entitlement to enforce, or None when this site is unrestricted."""
    if not enforcement_switch():
        return None
    return current()


def describe() -> dict[str, Any]:
    ent = current()
    return {
        "switch": enforcement_switch(),
        "enforcing": active() is not None,
        "source": ent.source if ent else None,
        "features": len(ent.features) if ent else 0,
        "digest": ent.digest if ent else None,
    }
