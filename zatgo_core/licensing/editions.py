"""Edition operations on the issuer site: save, duplicate, archive, compare, export / import, preset seeding.

Every write goes through the ZG Edition document (its controller holds the rules: issuer site, System Manager,
valid features, no missing dependency when Active, version bump). Reads work everywhere for those who may read
ZG Edition. Imports are previewed first and recorded in ZG Audit Log.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import frappe
from frappe import _

from zatgo_core.licensing import edition_config, inspector, issuer, registry

DOCTYPE = "ZG Edition"


def _is_single(doctype: str) -> bool:
    return bool(frappe.db.get_value("DocType", doctype, "issingle"))


def inspect(features: Mapping[str, Any] | list, platforms: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return inspector.inspect(features, platforms=platforms, installed=frappe.get_installed_apps(),
                             is_single=_is_single)


# -- reads --------------------------------------------------------------------------------------------------------

def list_editions() -> list[dict[str, Any]]:
    return frappe.get_list(
        DOCTYPE,
        fields=["name", "edition_id", "edition_name", "status", "version", "preset", "feature_count", "module_count",
                "missing_count", "modified"],
        order_by="edition_name asc",
        limit_page_length=0,
    )


def get_config(edition_id: str) -> dict[str, Any]:
    doc = frappe.get_doc(DOCTYPE, edition_id)
    doc.check_permission("read")
    return doc.to_config()


def compare(a: str, b: str) -> dict[str, Any]:
    return edition_config.compare(get_config(a), get_config(b))


def export(edition_id: str) -> dict[str, Any]:
    return edition_config.export_payload(get_config(edition_id))


# -- writes -------------------------------------------------------------------------------------------------------

def _apply(doc, config: Mapping[str, Any]) -> None:
    lic = config.get("licence_defaults") or {}
    platforms = config.get("platforms") or {}
    doc.update({
        "edition_name": config.get("edition_name"),
        "description": config.get("description") or "",
        "status": config.get("status") or "Draft",
        "platform_desk": int(bool(platforms.get("desk"))),
        "platform_desktop": int(bool(platforms.get("desktop"))),
        "platform_mobile": int(bool(platforms.get("mobile"))),
        "licence_type": lic.get("licence_type") or edition_config.DEFAULT_LICENCE["licence_type"],
        "duration_days": lic.get("duration_days", 0),
        "trial_days": lic.get("trial_days", 0),
        "max_users": lic.get("max_users", 0),
        "max_companies": lic.get("max_companies", 0),
        "default_roles": "\n".join(config.get("default_roles") or []),
    })
    if config.get("preset") and doc.is_new():
        doc.preset = config["preset"]
    doc.set("features", [])
    for fid, actions in edition_config.normalise_features(config.get("features") or {}).items():
        doc.append("features", {"feature": fid, "actions": ", ".join(actions)})


def save(config: Mapping[str, Any]) -> dict[str, Any]:
    """Create or update an edition from a config (the builder's payload). Returns the saved config."""
    issuer.require_issuer_manager()
    edition_id = str(config.get("edition_id") or "").strip()
    if frappe.db.exists(DOCTYPE, edition_id):
        doc = frappe.get_doc(DOCTYPE, edition_id)
    else:
        doc = frappe.new_doc(DOCTYPE)
        doc.edition_id = edition_id
    _apply(doc, config)
    doc.save()
    return doc.to_config()


def duplicate(edition_id: str, new_id: str, new_name: str) -> dict[str, Any]:
    issuer.require_issuer_manager()
    source = get_config(edition_id)
    if frappe.db.exists(DOCTYPE, new_id):
        frappe.throw(_("An edition with ID {0} already exists.").format(new_id))
    copy = {**source, "edition_id": new_id, "edition_name": new_name, "status": "Draft", "version": 1,
            "preset": source.get("preset") or edition_id}
    return save(copy)


def set_status(edition_id: str, status: str) -> dict[str, Any]:
    """Archive (status Archived) or bring back (Draft / Active). Editions are never deleted once used."""
    issuer.require_issuer_manager()
    if status not in edition_config.STATUSES:
        frappe.throw(_("Unknown status {0}").format(status))
    doc = frappe.get_doc(DOCTYPE, edition_id)
    doc.status = status
    doc.save()
    return doc.to_config()


# -- import -------------------------------------------------------------------------------------------------------

def _file_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _parse(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            frappe.throw(_("The file is not valid JSON."))
    if not isinstance(payload, dict):
        frappe.throw(_("An edition file is a JSON object."))
    payload = dict(payload)
    payload.pop("resolved", None)  # informational; recomputed from this app's registry
    return edition_config.migrate_config(payload)


def preview_import(payload: Any) -> dict[str, Any]:
    """What importing this file would do. Changes nothing."""
    config = _parse(payload)
    problems = edition_config.validate_config(config)
    out: dict[str, Any] = {"edition_id": config.get("edition_id"), "edition_name": config.get("edition_name"),
                           "problems": problems, "action": "refuse" if problems else "create", "conflict": False,
                           "diff": None, "inspection": None}
    if problems:
        return out
    config = edition_config.build_config(
        edition_id=config["edition_id"], edition_name=config["edition_name"], description=config.get("description", ""),
        features=config["features"], status=config.get("status", "Draft"), platforms=config.get("platforms"),
        licence_defaults=config.get("licence_defaults"), default_roles=config.get("default_roles", ()),
        preset=config.get("preset"),
    )
    out["inspection"] = inspect(config["features"], config["platforms"])
    if config["status"] == "Active" and out["inspection"]["missing"]:
        out["problems"] = ["the file is Active but misses dependencies; it would be imported as a Draft"]
        config["status"] = "Draft"
    if frappe.db.exists(DOCTYPE, config["edition_id"]):
        current = get_config(config["edition_id"])
        same = edition_config.grant_hash(current) == edition_config.grant_hash(config) and \
            current["edition_name"] == config["edition_name"]
        out["action"] = "unchanged" if same else "update"
        out["conflict"] = not same
        out["diff"] = edition_config.compare(current, config)
    out["config"] = config
    return out


def import_config(payload: Any, overwrite: bool = False) -> dict[str, Any]:
    """Import an edition file: create it, or replace an existing edition only when `overwrite` is set."""
    issuer.require_issuer_manager()
    preview = preview_import(payload)
    if preview["action"] == "refuse":
        frappe.throw("<br>".join(frappe.utils.escape_html(p) for p in preview["problems"]), title=_("Cannot import"))
    if preview["conflict"] and not overwrite:
        frappe.throw(_("Edition {0} already exists with different content. Confirm the overwrite to replace it.")
                     .format(preview["edition_id"]), title=_("Edition exists"))
    result = preview["config"] if preview["action"] == "unchanged" else save(preview["config"])
    _log_import(preview, _file_hash(_parse(payload)))
    return {"action": preview["action"], "config": result}


def _log_import(preview: Mapping[str, Any], file_hash: str) -> None:
    frappe.get_doc({
        "doctype": "ZG Audit Log", "doctype_name": DOCTYPE, "document_name": preview["edition_id"],
        "fieldname": "import", "old_value": None,
        "new_value": json.dumps({"action": preview["action"], "file_hash": file_hash}),
        "changed_by": frappe.session.user, "change_date": frappe.utils.today(), "change_time": frappe.utils.nowtime(),
        "reason": _("Edition configuration imported"), "app_name": "zatgo_core",
    }).insert(ignore_permissions=True)


def import_history(limit: int = 50) -> list[dict[str, Any]]:
    return frappe.get_all(
        "ZG Audit Log",
        filters={"doctype_name": DOCTYPE, "fieldname": "import"},
        fields=["document_name", "new_value", "changed_by", "creation"],
        order_by="creation desc", limit_page_length=limit,
    )


# -- presets ------------------------------------------------------------------------------------------------------

def seed_presets() -> int:
    """On the issuer site: create the shipped preset editions that do not exist yet. An existing edition with a
    preset's id is left exactly as it is (someone may have changed it). Returns how many were created."""
    if not issuer.is_issuer_site():
        return 0
    created = 0
    for preset in edition_config.presets():
        if frappe.db.exists(DOCTYPE, preset["edition_id"]):
            continue
        save(preset)
        created += 1
    return created


def registry_payload() -> dict[str, Any]:
    """Modules and features for the edition builder, with this site's availability."""
    installed = set(frappe.get_installed_apps())
    return {
        "modules": [{"id": m.id, "label": m.label, "category": m.category, "description": m.description,
                     "available": m.source_app in installed} for m in registry.modules()],
        "features": [{
            "id": f.id, "module": f.module, "label": f.label, "description": f.description,
            "foundation": f.foundation, "available": f.source_app in installed, "source_app": f.source_app,
            "platforms": list(f.platforms), "actions": list(edition_config.feature_actions(f)),
            "requires": {fid: list(a) for fid, a in f.requires},
        } for f in registry.features() if not f.retired],
        "actions": list(registry.ACTIONS),
        "platforms": list(registry.PLATFORMS),
        "licence_types": list(edition_config.LICENCE_TYPES),
        "statuses": list(edition_config.STATUSES),
        "registry_hash": registry.registry_hash(),
    }
