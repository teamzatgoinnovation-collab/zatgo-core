"""Edition configuration: the portable, canonical form of an edition, its validation, hash, diff and presets.

An **edition** is a commercial product configuration: which registry features it includes (optionally narrowed to
fewer actions), on which platforms, with which licence defaults. It is a *template*: a licence issued from it
(Phase 5) carries its own signed copy of the resolved features, so changing an edition never changes a licence
that was already issued.

The edition file (`type: "zatgo.edition"`) is NOT a licence (`type: "zatgo.licence"`): it is unsigned and is never
trusted as authority on a customer site. Import refuses a licence file and vice versa.

Pure Python (no database): the DocType controller, the API and the tests share these rules.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from typing import Any, Iterable, Mapping

from zatgo_core.licensing import registry

FILE_TYPE = "zatgo.edition"
LICENCE_FILE_TYPE = "zatgo.licence"
SCHEMA_VERSION = 1
PRODUCT_ID = "zatgo_erp"

STATUSES = ("Draft", "Active", "Archived")
LICENCE_TYPES = ("Trial", "Monthly", "Yearly", "Lifetime", "Custom Duration", "Perpetual")
EDITION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,59}$")

DEFAULT_LICENCE = {
    "licence_type": "Yearly", "duration_days": 365, "trial_days": 30, "max_users": 5, "max_companies": 1,
}
# Limits: 0 means "no limit". Duration is ignored for Lifetime / Perpetual.
_LIMIT_KEYS = ("duration_days", "trial_days", "max_users", "max_companies")

PRESETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editions")


# -- features -----------------------------------------------------------------------------------------------------

def feature_actions(feature: registry.Feature) -> tuple[str, ...]:
    """Every action a feature can grant (the union of its DocType grants), in ACTIONS order."""
    have = {a for g in feature.doctypes for a in g.actions}
    return tuple(a for a in registry.ACTIONS if a in have)


def normalise_features(features: Mapping[str, Iterable[str]] | Iterable[str]) -> dict[str, list[str]]:
    """{feature_id: [actions]} with actions in ACTIONS order; a list of ids means 'all actions' ([])."""
    if not isinstance(features, Mapping):
        features = {fid: [] for fid in features}
    out: dict[str, list[str]] = {}
    for fid, actions in features.items():
        acts = [a for a in registry.ACTIONS if a in set(actions or ())]
        out[str(fid)] = acts
    return dict(sorted(out.items()))


def feature_problems(features: Mapping[str, Iterable[str]]) -> list[str]:
    problems = []
    for fid, actions in features.items():
        feature = registry.get_feature(fid)
        if feature is None:
            problems.append(f"{fid}: unknown feature")
            continue
        if feature.retired:
            problems.append(f"{fid}: retired feature")
        if feature.foundation:
            problems.append(f"{fid}: foundation features are part of every edition, do not list them")
        actions = list(actions or ())
        if bad := [a for a in actions if a not in registry.ACTIONS]:
            problems.append(f"{fid}: unknown actions {bad}")
            continue
        allowed = set(feature_actions(feature))
        if actions and not allowed:
            problems.append(f"{fid}: has no DocTypes, so it takes no actions")
        elif extra := [a for a in actions if a not in allowed]:
            problems.append(f"{fid}: does not grant {extra}")
    return problems


def effective_actions(feature: registry.Feature, narrowed: Iterable[str]) -> tuple[str, ...]:
    """The actions an edition gives on a feature: all of them, or the narrowed subset."""
    narrowed = tuple(narrowed or ())
    return narrowed if narrowed else feature_actions(feature)


# -- the canonical config -----------------------------------------------------------------------------------------

def build_config(
    *,
    edition_id: str,
    edition_name: str,
    features: Mapping[str, Iterable[str]] | Iterable[str],
    description: str = "",
    version: int = 1,
    status: str = "Draft",
    platforms: Mapping[str, Any] | None = None,
    licence_defaults: Mapping[str, Any] | None = None,
    default_roles: Iterable[str] = (),
    preset: str | None = None,
) -> dict[str, Any]:
    platforms = platforms or {"desk": 1}
    return {
        "type": FILE_TYPE,
        "schema_version": SCHEMA_VERSION,
        "product_id": PRODUCT_ID,
        "edition_id": edition_id,
        "edition_name": edition_name,
        "description": description or "",
        "version": int(version or 1),
        "status": status,
        "preset": preset or None,
        "platforms": {p: int(bool(platforms.get(p))) for p in registry.PLATFORMS},
        "licence_defaults": _licence_defaults(licence_defaults),
        "default_roles": sorted({r for r in default_roles if r}),
        "features": normalise_features(features),
    }


def _licence_defaults(value: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_LICENCE)
    for key, v in (value or {}).items():
        if key in out:
            out[key] = v
    for key in _LIMIT_KEYS:
        try:
            out[key] = int(out[key] or 0)
        except (TypeError, ValueError):
            out[key] = out[key]  # left for validate_config to report
    return out


def grant_hash(config: Mapping[str, Any]) -> str:
    """Hash of what the edition grants -- a change here bumps its version. Name, description and status don't."""
    payload = {k: config.get(k) for k in ("features", "platforms", "licence_defaults", "default_roles")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def validate_config(config: Mapping[str, Any]) -> list[str]:
    """Problems with an edition config (an imported file or a form about to be saved); [] when sound."""
    problems: list[str] = []
    ftype = config.get("type")
    if ftype == LICENCE_FILE_TYPE:
        return ["this is a licence file, not an edition configuration -- import it on the Licence page"]
    if ftype != FILE_TYPE:
        problems.append(f"type must be {FILE_TYPE!r}")
    try:
        schema = int(config.get("schema_version") or 0)
    except (TypeError, ValueError):
        schema = 0
    if schema < 1 or schema > SCHEMA_VERSION:
        problems.append(f"unsupported schema_version {config.get('schema_version')!r} (this app reads 1..{SCHEMA_VERSION})")
    if config.get("product_id") != PRODUCT_ID:
        problems.append(f"product_id must be {PRODUCT_ID!r}")
    eid = config.get("edition_id") or ""
    if not EDITION_ID_PATTERN.match(str(eid)):
        problems.append("edition_id must be 2-60 lower-case letters, digits or _ and start with a letter")
    if not str(config.get("edition_name") or "").strip():
        problems.append("edition_name is required")
    if config.get("status", "Draft") not in STATUSES:
        problems.append(f"status must be one of {', '.join(STATUSES)}")
    platforms = config.get("platforms") or {}
    if not isinstance(platforms, Mapping) or set(platforms) - set(registry.PLATFORMS):
        problems.append(f"platforms must be a map of {', '.join(registry.PLATFORMS)}")
    elif not any(platforms.values()):
        problems.append("an edition needs at least one platform")
    lic = config.get("licence_defaults") or {}
    if lic.get("licence_type") not in LICENCE_TYPES:
        problems.append(f"licence_type must be one of {', '.join(LICENCE_TYPES)}")
    for key in _LIMIT_KEYS:
        value = lic.get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.append(f"licence_defaults.{key} must be a whole number >= 0 (0 = no limit)")
    features = config.get("features")
    if not isinstance(features, Mapping):
        problems.append("features must be a map of feature id -> actions")
    else:
        problems.extend(feature_problems(features))
    return problems


def migrate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Bring an older file up to SCHEMA_VERSION. There is only version 1 so far; a newer file is refused by
    validate_config rather than guessed at."""
    return dict(config)


# -- derived views ------------------------------------------------------------------------------------------------

def resolved(config: Mapping[str, Any]) -> dict[str, Any]:
    """Informational block of an exported file: what the features map to in this app's registry. Ignored on
    import (the importing app recomputes it from its own registry)."""
    features = config.get("features") or {}
    deps = registry.resolve_requirements(features)
    doctype_mappings: dict[str, set[str]] = {}
    reports, workspaces, modules = set(), set(), set()
    for fid, narrowed in features.items():
        feature = registry.get_feature(fid)
        if feature is None:
            continue
        modules.add(feature.module)
        acts = set(effective_actions(feature, narrowed))
        for g in feature.doctypes:
            doctype_mappings.setdefault(g.doctype, set()).update(a for a in g.actions if a in acts)
        reports.update(feature.reports)
        workspaces.update(feature.workspaces)
    return {
        "registry_hash": registry.registry_hash(),
        "modules": sorted(modules),
        "dependencies": deps["missing"],
        "doctype_mappings": {k: [a for a in registry.ACTIONS if a in v] for k, v in sorted(doctype_mappings.items())},
        "report_mappings": sorted(reports),
        "workspace_mappings": sorted(workspaces),
    }


def export_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    return {**config, "resolved": resolved(config)}


def compare(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    fa, fb = a.get("features") or {}, b.get("features") or {}
    both = sorted(set(fa) & set(fb))
    return {
        "a": a.get("edition_id"), "b": b.get("edition_id"),
        "only_a": sorted(set(fa) - set(fb)),
        "only_b": sorted(set(fb) - set(fa)),
        "both": both,
        "actions_differ": [
            {"feature": fid, "a": list(fa[fid]), "b": list(fb[fid])} for fid in both if list(fa[fid]) != list(fb[fid])
        ],
        "platforms": {p: [(a.get("platforms") or {}).get(p, 0), (b.get("platforms") or {}).get(p, 0)]
                      for p in registry.PLATFORMS
                      if (a.get("platforms") or {}).get(p, 0) != (b.get("platforms") or {}).get(p, 0)},
        "licence_defaults": {k: [v, (b.get("licence_defaults") or {}).get(k)]
                             for k, v in (a.get("licence_defaults") or {}).items()
                             if v != (b.get("licence_defaults") or {}).get(k)},
    }


# -- presets ------------------------------------------------------------------------------------------------------

@lru_cache(maxsize=None)
def presets() -> tuple[dict[str, Any], ...]:
    """The starter editions shipped in licensing/editions/*.json, as canonical configs (Active unless the file
    says otherwise -- the empty Custom Edition is a Draft to copy from).

    A preset file may say `"features": "*"` (Enterprise): every live, non-foundation feature."""
    out = []
    for name in sorted(os.listdir(PRESETS_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(PRESETS_DIR, name), encoding="utf-8") as fh:
            spec = json.load(fh)
        features = spec.get("features") or []
        if features == "*":
            features = [f.id for f in registry.features() if not f.retired and not f.foundation]
        out.append(build_config(
            edition_id=spec["edition_id"], edition_name=spec["edition_name"], description=spec.get("description", ""),
            features=features, status=spec.get("status", "Active"), platforms=spec.get("platforms"),
            licence_defaults=spec.get("licence_defaults"), default_roles=spec.get("default_roles", ()),
            preset=spec["edition_id"],
        ))
    out.sort(key=lambda c: c["edition_id"])
    return tuple(out)


def get_preset(edition_id: str) -> dict[str, Any] | None:
    return next((dict(p) for p in presets() if p["edition_id"] == edition_id), None)
