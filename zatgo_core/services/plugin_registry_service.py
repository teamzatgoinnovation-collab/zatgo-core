"""Register and query plugin applications / setting sections."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import now_datetime

from zatgo_core.constants.settings import DOCTYPES
from zatgo_core.permissions.settings_visibility import can_manage_registry, can_see_roles
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

APP_DT = DOCTYPES["REGISTERED_APPLICATION"]
SECTION_DT = DOCTYPES["SETTING_SECTION"]
HISTORY_DT = DOCTYPES["CONFIG_HISTORY"]


class PluginRegistryService:
    """Upsert manifests and expose permission-filtered application trees."""

    @classmethod
    def register_application(
        cls, manifest: dict[str, Any], *, ignore_permissions: bool = False
    ) -> dict[str, Any]:
        if not ignore_permissions and not can_manage_registry():
            frappe.throw(frappe._("Not permitted to register applications"), frappe.PermissionError)

        if not frappe.db.exists("DocType", APP_DT):
            frappe.throw(frappe._("{0} DocType is not available").format(APP_DT))

        app_key = (manifest.get("app_key") or "").strip()
        if not app_key:
            frappe.throw(frappe._("app_key is required"))

        sections = list(manifest.get("sections") or [])
        payload = {k: v for k, v in manifest.items() if k != "sections"}
        payload["manifest_json"] = json.dumps(manifest, default=str)

        existing = frappe.db.exists(APP_DT, app_key)
        if existing:
            doc = frappe.get_doc(APP_DT, existing)
            for field in (
                "title",
                "version",
                "icon",
                "category",
                "menu_order",
                "enabled",
                "visible",
                "roles",
                "depends_on",
                "description",
                "settings_route",
                "manifest_json",
            ):
                if field in payload and payload[field] is not None:
                    doc.set(field, payload[field])
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.get_doc({"doctype": APP_DT, "app_key": app_key, **payload})
            doc.insert(ignore_permissions=True)

        cls._sync_sections(app_key, sections)
        cls._history(app_key, None, "Register", None, manifest)
        logger.info("Registered application %s sections=%s", app_key, len(sections))
        return {"app_key": app_key, "sections": len(sections)}

    @classmethod
    def _sync_sections(cls, app_key: str, sections: list[dict[str, Any]]) -> None:
        keep_keys: set[str] = set()
        for idx, section in enumerate(sections):
            key = (section.get("section_key") or "").strip()
            if not key:
                continue
            keep_keys.add(key)
            defaults = section.get("defaults_json")
            if isinstance(defaults, dict):
                defaults_json = json.dumps(defaults)
            else:
                defaults_json = defaults or None

            values = {
                "application": app_key,
                "section_key": key,
                "label": section.get("label") or key,
                "icon": section.get("icon"),
                "sort_order": section.get("sort_order", (idx + 1) * 10),
                "enabled": section.get("enabled", 1),
                "is_group": section.get("is_group", 0),
                "link_doctype": section.get("link_doctype") or "",
                "component": section.get("component") or "",
                "roles": section.get("roles") or "",
                "description": section.get("description") or "",
                "defaults_json": defaults_json,
            }
            name = frappe.db.exists(
                SECTION_DT, {"application": app_key, "section_key": key}
            )
            if name:
                doc = frappe.get_doc(SECTION_DT, name)
                doc.update(values)
                doc.save(ignore_permissions=True)
            else:
                frappe.get_doc({"doctype": SECTION_DT, **values}).insert(
                    ignore_permissions=True
                )

        # Remove sections no longer in manifest
        for row in frappe.get_all(
            SECTION_DT, filters={"application": app_key}, fields=["name", "section_key"]
        ):
            if row.section_key not in keep_keys:
                frappe.delete_doc(SECTION_DT, row.name, ignore_permissions=True, force=1)

    @classmethod
    def list_applications(cls) -> list[dict[str, Any]]:
        if not frappe.db.exists("DocType", APP_DT):
            return []
        rows = frappe.get_all(
            APP_DT,
            fields=[
                "name",
                "app_key",
                "title",
                "version",
                "icon",
                "category",
                "menu_order",
                "enabled",
                "visible",
                "roles",
                "depends_on",
                "description",
                "settings_route",
            ],
            order_by="menu_order asc, title asc",
            limit_page_length=500,
        )
        out = []
        for row in rows:
            if not row.get("visible"):
                continue
            if not can_see_roles(row.get("roles")):
                continue
            out.append(row)
        return out

    @classmethod
    def get_application(cls, app_key: str) -> dict[str, Any] | None:
        if not frappe.db.exists(APP_DT, app_key):
            return None
        app = frappe.get_doc(APP_DT, app_key)
        if not app.visible or not can_see_roles(app.roles):
            return None
        sections = frappe.get_all(
            SECTION_DT,
            filters={"application": app_key, "enabled": 1},
            fields=[
                "name",
                "section_key",
                "label",
                "parent_section",
                "is_group",
                "icon",
                "sort_order",
                "link_doctype",
                "component",
                "roles",
                "description",
                "defaults_json",
            ],
            order_by="sort_order asc",
            limit_page_length=500,
        )
        visible_sections = [
            s for s in sections if can_see_roles(s.get("roles") or app.roles)
        ]
        data = app.as_dict()
        data["sections"] = visible_sections
        return data

    @classmethod
    def search_settings(cls, query: str) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []
        like = f"%{query}%"
        apps = {
            a.app_key: a
            for a in cls.list_applications()
        }
        rows = frappe.get_all(
            SECTION_DT,
            filters={"enabled": 1},
            or_filters={"label": ("like", like), "section_key": ("like", like)},
            fields=[
                "name",
                "application",
                "section_key",
                "label",
                "icon",
                "link_doctype",
                "component",
                "roles",
            ],
            limit_page_length=50,
        )
        out = []
        for row in rows:
            app = apps.get(row.application)
            if not app:
                continue
            if not can_see_roles(row.get("roles") or app.get("roles")):
                continue
            out.append(
                {
                    **row,
                    "app_title": app.get("title"),
                    "app_key": row.application,
                }
            )
        return out

    @classmethod
    def _history(
        cls,
        app_key: str | None,
        section_key: str | None,
        action: str,
        old: Any,
        new: Any,
        note: str | None = None,
    ) -> None:
        if not frappe.db.exists("DocType", HISTORY_DT):
            return
        try:
            frappe.get_doc(
                {
                    "doctype": HISTORY_DT,
                    "application": app_key,
                    "section_key": section_key,
                    "action": action,
                    "changed_by": frappe.session.user,
                    "changed_on": now_datetime(),
                    "old_payload": json.dumps(old, default=str) if old is not None else None,
                    "new_payload": json.dumps(new, default=str) if new is not None else None,
                    "note": note,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            logger.exception("config history write failed")
