"""Read-only "what would this edition refuse?" report for a live site (Phase 10 rollout aid).

Before enforcement is switched on for a site, run it with the edition (or feature set) the site is about to be
licensed for. It counts the documents the site created in the last N days for every DocType the licensing registry
maps, and says which of those the entitlement would refuse to create today. A non-empty `refused` list means the
edition is too small for how the site is really used: pick a larger one before enforcing.

Only counts are read: nothing is written, enforcement is not switched on, no licence is needed.

    bench --site <site> execute zatgo_core.licensing.usage_audit.report --kwargs '{"edition_id": "sales"}'
    bench --site <site> execute zatgo_core.licensing.usage_audit.report \\
        --kwargs '{"edition_id": "sales", "days": 180, "json": true}'

`edition_id` is a shipped preset (licensing/editions/*.json) or an edition on this site.
"""

from __future__ import annotations

import json as _json
from typing import Any

import frappe
from frappe.utils import add_days, today

from zatgo_core.licensing import edition_config, gate, registry
from zatgo_core.licensing.entitlement import Entitlement


def _filters(match: tuple[tuple[str, Any], ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field, value in match:
        out[field] = ["in", list(value)] if isinstance(value, tuple) else value
    return out


def _sample(doctype: str, match: tuple[tuple[str, Any], ...]) -> frappe._dict:
    """A stand-in document that matches the grant, for the gate's decision."""
    fields = {field: (value[0] if isinstance(value, tuple) else value) for field, value in match}
    return frappe._dict(doctype=doctype, **fields)


def _features_for(edition_id: str | None, features: dict[str, Any] | None) -> dict[str, Any]:
    if features is not None:
        return features
    if not edition_id:
        raise ValueError("give an edition_id or a features map")
    preset = edition_config.get_preset(edition_id)
    if preset is not None:
        return preset["features"]
    if frappe.db.exists("Edition", edition_id):
        return frappe.get_doc("Edition", edition_id).to_config()["features"]
    raise ValueError(f"unknown edition {edition_id!r}")


def audit(edition_id: str | None = None, days: int = 90, features: dict[str, Any] | None = None) -> dict[str, Any]:
    """{"edition", "days", "since", "refused": [...], "allowed": [...], "totals": {...}} (counts only)."""
    chosen = _features_for(edition_id, features)
    entitlement = Entitlement.from_features(chosen, source="usage-audit")
    since = add_days(today(), -int(days))
    refused: list[dict[str, Any]] = []
    allowed: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple]] = set()
    for doctype, grants in sorted(registry.doctype_index().items()):
        if not frappe.db.exists("DocType", doctype):
            continue
        meta = frappe.get_meta(doctype)
        if meta.issingle or meta.istable:
            continue
        for _feature, grant in grants:
            key = (doctype, grant.match)
            if key in seen:
                continue
            seen.add(key)
            count = frappe.db.count(doctype, {"creation": [">=", since], **_filters(grant.match)})
            if not count:
                continue
            verdict = gate.decide(doctype, "create", _sample(doctype, grant.match), entitlement)
            row = {"doctype": doctype, "when": dict(grant.match) if grant.match else None, "created": count}
            if verdict["allowed"]:
                allowed.append(row)
            else:
                row["needs_one_of"] = verdict["features"]
                refused.append(row)
    refused.sort(key=lambda r: -r["created"])
    return {
        "edition": edition_id, "days": int(days), "since": str(since),
        "refused": refused, "allowed": allowed,
        "totals": {"refused_doctypes": len(refused), "refused_documents": sum(r["created"] for r in refused),
                   "allowed_doctypes": len(allowed), "allowed_documents": sum(r["created"] for r in allowed)},
    }


def report(edition_id: str | None = None, days: int = 90, json: bool = False) -> dict[str, Any]:
    """`bench execute` entry: prints a readable summary (or JSON) and returns the audit."""
    data = audit(edition_id, int(days))
    if json:
        print(_json.dumps(data, indent=1, default=str))
        return data
    t = data["totals"]
    print(f"Edition {edition_id!r}, documents created since {data['since']} ({data['days']} days)")
    print(f"  would still be allowed: {t['allowed_documents']} documents in {t['allowed_doctypes']} DocTypes")
    if not data["refused"]:
        print("  would be refused: nothing -- this edition covers how the site is used")
    else:
        print(f"  WOULD BE REFUSED: {t['refused_documents']} documents in {t['refused_doctypes']} DocTypes "
              "(the edition is too small for this site)")
        for row in data["refused"]:
            cond = f" [{', '.join(f'{k}={v}' for k, v in row['when'].items())}]" if row["when"] else ""
            print(f"    {row['created']:>6}  {row['doctype']}{cond}  needs: {', '.join(row['needs_one_of'])}")
    return data
