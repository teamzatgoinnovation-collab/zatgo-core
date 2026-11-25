"""Edition builder API (Desk page `zg-edition-builder`).

Paths: zatgo_core.api.v1.licensing.editions.<method>

Reads need read access to Edition (System Manager, ZatGo Application Admin, ZatGo Read Only). Writes are POST only and
go through the Edition controller, which allows them on the licence issuer site and for a System Manager only
(licensing/issuer.py) -- the page's own checks are courtesy. Server errors are raised (Frappe returns them with
the right HTTP status); success answers use the standard envelope.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from zatgo_core.api.response import ok
from zatgo_core.api.validators import require_str
from zatgo_core.licensing import editions, issuer
from zatgo_core.services.ui_apps import asset_url

DOCTYPE = editions.DOCTYPE


def _require_read() -> None:
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw(_("Not permitted to read editions."), frappe.PermissionError)


def _can_edit() -> bool:
    return issuer.is_issuer_site() and (
        frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()
    )


def _json(value: Any, name: str) -> Any:
    try:
        return frappe.parse_json(value) if isinstance(value, str) else value
    except ValueError:
        frappe.throw(_("{0} is not valid JSON").format(name))


@frappe.whitelist()
def get_builder() -> dict[str, Any]:
    _require_read()
    return ok({
        **editions.registry_payload(),
        "editions": editions.list_editions(),
        "is_issuer": issuer.is_issuer_site(),
        "can_edit": _can_edit(),
        "presets": [p["edition_id"] for p in editions.edition_config.presets()],
        "css": asset_url("css/zg_edition_builder.css"),
    })


@frappe.whitelist()
def get_edition(edition_id: str) -> dict[str, Any]:
    _require_read()
    config = editions.get_config(require_str(edition_id, "edition_id"))
    return ok({"config": config, "inspection": editions.inspect(config["features"], config["platforms"])})


@frappe.whitelist(methods=["POST"])
def inspect(features: Any, platforms: Any = None) -> dict[str, Any]:
    """Dependency Inspector for an unsaved selection (the builder calls it as boxes are ticked)."""
    _require_read()
    return ok(editions.inspect(_json(features, "features") or {}, _json(platforms, "platforms")))


@frappe.whitelist(methods=["POST"])
def save_edition(config: Any) -> dict[str, Any]:
    issuer.require_issuer_manager()  # before reading the payload: a refusal must not depend on its content
    config = _json(config, "config") or {}
    saved = editions.save(config)
    return ok({"config": saved, "inspection": editions.inspect(saved["features"], saved["platforms"])})


@frappe.whitelist(methods=["POST"])
def duplicate_edition(edition_id: str, new_id: str, new_name: str) -> dict[str, Any]:
    return ok(editions.duplicate(require_str(edition_id, "edition_id"), require_str(new_id, "new_id"),
                                 require_str(new_name, "new_name")))


@frappe.whitelist(methods=["POST"])
def set_edition_status(edition_id: str, status: str) -> dict[str, Any]:
    return ok(editions.set_status(require_str(edition_id, "edition_id"), require_str(status, "status")))


@frappe.whitelist()
def compare_editions(a: str, b: str) -> dict[str, Any]:
    _require_read()
    return ok(editions.compare(require_str(a, "a"), require_str(b, "b")))


@frappe.whitelist()
def export_edition(edition_id: str) -> dict[str, Any]:
    _require_read()
    return ok(editions.export(require_str(edition_id, "edition_id")))


@frappe.whitelist(methods=["POST"])
def preview_import(payload: Any) -> dict[str, Any]:
    issuer.require_issuer_manager()
    return ok(editions.preview_import(payload))


@frappe.whitelist(methods=["POST"])
def import_edition(payload: Any, overwrite: Any = 0) -> dict[str, Any]:
    return ok(editions.import_config(payload, overwrite=bool(frappe.utils.cint(overwrite))))


@frappe.whitelist()
def import_history() -> dict[str, Any]:
    _require_read()
    return ok(editions.import_history())
