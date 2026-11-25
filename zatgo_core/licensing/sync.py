"""Project the licensing registry (code) into `Module` / `Feature` (read-only DocTypes).

One way, like plugins/discover.py: the code is the truth, the rows are what the Desk and (later) the edition
builder show and link to. Idempotent -- a row is written only when what the code says changed, so a re-run
writes nothing. Rows are never deleted: a feature that left the code is marked retired (the id lock test makes
that a deliberate act), because a signed licence may still name it.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from zatgo_core.licensing import registry

MODULE_DOCTYPE = "Module"
FEATURE_DOCTYPE = "Feature"


def refuse_manual_change(doc: Any) -> None:
    """Controller guard: only this sync (and install / migrate / patches) may write the projection."""
    flags = frappe.flags
    if flags.in_licensing_sync or flags.in_install or flags.in_migrate or flags.in_patch:
        return
    frappe.throw(
        _("{0} is generated from the ZatGo licensing registry and cannot be changed by hand.").format(_(doc.doctype)),
        frappe.PermissionError,
    )


def _lines(values) -> str:
    return "\n".join(values)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False)


def module_row(module: registry.Module, installed: set[str], reg_hash: str) -> dict[str, Any]:
    return {
        "module_id": module.id,
        "label": module.label,
        "category": module.category,
        "description": module.description,
        "icon": module.icon,
        "display_order": module.order,
        "source_app": module.source_app,
        "available": int(module.source_app in installed),
        "feature_count": len([f for f in registry.features_of_module(module.id) if not f.retired]),
        "registry_hash": reg_hash,
    }


def feature_row(feature: registry.Feature, installed: set[str]) -> dict[str, Any]:
    return {
        "feature_id": feature.id,
        "label": feature.label,
        "module": feature.module,
        "description": feature.description,
        "available": int(feature.source_app in installed and not feature.retired),
        "foundation": int(feature.foundation),
        "retired": int(feature.retired),
        "source_app": feature.source_app,
        "platforms": ", ".join(feature.platforms),
        "app_key": feature.app_key or "",
        "industry": feature.industry or "",
        "vansalex_keys": _lines(feature.vansalex_keys),
        "doctype_map": _json([g.as_dict() for g in feature.doctypes]),
        "requires": _json({fid: list(acts) for fid, acts in feature.requires}),
        "reports": _lines(feature.reports),
        "pages": _lines(feature.pages),
        "workspaces": _lines(feature.workspaces),
        "api_prefixes": _lines(feature.api_prefixes),
        "fingerprint": feature.fingerprint(),
    }


def _normal(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    return value


def _upsert(doctype: str, name: str, row: dict[str, Any]) -> bool:
    """Insert or update one row; False when it already says exactly this."""
    fields = list(row)
    current = frappe.db.get_value(doctype, name, fields, as_dict=True)
    if current is not None and all(_normal(current.get(k)) == _normal(v) for k, v in row.items()):
        return False
    if current is None:
        frappe.get_doc({"doctype": doctype, **row}).insert(ignore_permissions=True)
    else:
        doc = frappe.get_doc(doctype, name)
        doc.update(row)
        doc.save(ignore_permissions=True)
    return True


def sync_registry() -> dict[str, int]:
    """Bring Module / Feature in line with the code. Returns how many rows it wrote."""
    problems = registry.validate()
    if problems:
        # A broken registry is a code bug caught by the unit test; never half-project it.
        raise ValueError("licensing registry is invalid: " + "; ".join(problems[:5]))
    installed = set(frappe.get_installed_apps())
    reg_hash = registry.registry_hash()
    written = {"modules": 0, "features": 0, "retired": 0}
    previous = frappe.flags.in_licensing_sync
    frappe.flags.in_licensing_sync = True
    try:
        for module in registry.modules():
            written["modules"] += _upsert(MODULE_DOCTYPE, module.id, module_row(module, installed, reg_hash))
        live = set()
        for feature in registry.features():
            live.add(feature.id)
            written["features"] += _upsert(FEATURE_DOCTYPE, feature.id, feature_row(feature, installed))
        for name in frappe.get_all(FEATURE_DOCTYPE, filters={"retired": 0}, pluck="name"):
            if name not in live:
                frappe.db.set_value(FEATURE_DOCTYPE, name, {"retired": 1, "available": 0},
                                    update_modified=False)
                written["retired"] += 1
    finally:
        frappe.flags.in_licensing_sync = previous
    return written
