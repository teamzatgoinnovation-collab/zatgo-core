"""Load / save settings for a registered section."""

from __future__ import annotations

import json
from typing import Any

import frappe

from zatgo_core import __version__
from zatgo_core.constants.settings import DOCTYPES
from zatgo_core.permissions.guards import assert_can_write_settings
from zatgo_core.permissions.settings_visibility import can_see_roles
from zatgo_core.repositories.settings_repository import SettingsRepository
from zatgo_core.services.plugin_registry_service import PluginRegistryService
from zatgo_core.utils.logging import get_logger

logger = get_logger("system")

SECTION_DT = DOCTYPES["SETTING_SECTION"]
APP_DT = DOCTYPES["REGISTERED_APPLICATION"]
PROFILE_DT = DOCTYPES["CONFIG_PROFILE"]

# In-memory / site-storage key for component-backed prefs (module_preferences)
COMPONENT_STORE_DOCTYPE = DOCTYPES["FEATURE_FLAG"]  # unused sentinel


class ConfigLoaderService:
    """Map setting sections to DocTypes, component JSON, or pending stubs."""

    @classmethod
    def _get_section(cls, app_key: str, section_key: str) -> dict[str, Any]:
        name = frappe.db.exists(
            SECTION_DT, {"application": app_key, "section_key": section_key}
        )
        if not name:
            frappe.throw(frappe._("Unknown section {0}/{1}").format(app_key, section_key))
        section = frappe.get_doc(SECTION_DT, name).as_dict()
        app = frappe.get_doc(APP_DT, app_key)
        if not can_see_roles(section.get("roles") or app.roles):
            frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
        return section

    @classmethod
    def get_settings(cls, app_key: str, section_key: str) -> dict[str, Any]:
        section = cls._get_section(app_key, section_key)
        host = cls._resolve_host(section)
        return {
            "app_key": app_key,
            "section_key": section_key,
            "label": section.get("label"),
            "host": host,
            "data": cls._load_data(section, host),
        }

    @classmethod
    def update_settings(
        cls, app_key: str, section_key: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        assert_can_write_settings("apps")
        section = cls._get_section(app_key, section_key)
        host = cls._resolve_host(section)
        old = cls._load_data(section, host)

        if host["type"] == "doctype" and host.get("doctype"):
            dt = host["doctype"]
            meta = frappe.get_meta(dt)
            if meta.issingle:
                SettingsRepository.save_single(dt, values)
            else:
                frappe.throw(
                    frappe._(
                        "List DocType sections open in Desk; use Form for updates"
                    )
                )
        elif host["type"] == "component":
            cls._save_component_state(app_key, section_key, values)
        else:
            frappe.throw(frappe._("Section is not writable yet"))

        PluginRegistryService._history(app_key, section_key, "Update", old, values)
        return cls.get_settings(app_key, section_key)

    @classmethod
    def reset_settings(cls, app_key: str, section_key: str) -> dict[str, Any]:
        assert_can_write_settings("apps")
        section = cls._get_section(app_key, section_key)
        defaults = {}
        if section.get("defaults_json"):
            try:
                defaults = json.loads(section["defaults_json"])
            except json.JSONDecodeError:
                defaults = {}
        if not defaults:
            frappe.throw(frappe._("No defaults defined for this section"))
        result = cls.update_settings(app_key, section_key, defaults)
        PluginRegistryService._history(
            app_key, section_key, "Reset", None, defaults, note="reset to defaults"
        )
        return result

    @classmethod
    def validate_configuration(cls, app_key: str) -> dict[str, Any]:
        app = PluginRegistryService.get_application(app_key)
        if not app:
            frappe.throw(frappe._("Application not found or not visible"))
        issues: list[str] = []
        for section in app.get("sections") or []:
            if section.get("component") == "pending":
                issues.append(f"{section['section_key']}: pending configuration")
            link = section.get("link_doctype")
            if link and not frappe.db.exists("DocType", link):
                issues.append(f"{section['section_key']}: missing DocType {link}")
        return {
            "app_key": app_key,
            "ok": not issues,
            "issues": issues,
            "pending_count": sum(
                1
                for s in (app.get("sections") or [])
                if s.get("component") == "pending"
            ),
        }

    @classmethod
    def export_settings(cls, profile_name: str | None = None) -> dict[str, Any]:
        apps = PluginRegistryService.list_applications()
        payload: dict[str, Any] = {"applications": {}, "exported_by": frappe.session.user}
        for app in apps:
            key = app["app_key"]
            full = PluginRegistryService.get_application(key)
            if not full:
                continue
            app_payload = {}
            for section in full.get("sections") or []:
                try:
                    app_payload[section["section_key"]] = cls.get_settings(
                        key, section["section_key"]
                    )["data"]
                except Exception:
                    continue
            payload["applications"][key] = app_payload

        if profile_name and frappe.db.exists("DocType", PROFILE_DT):
            if frappe.db.exists(PROFILE_DT, profile_name):
                doc = frappe.get_doc(PROFILE_DT, profile_name)
            else:
                doc = frappe.get_doc(
                    {
                        "doctype": PROFILE_DT,
                        "profile_name": profile_name,
                        "environment": "Custom",
                    }
                )
                doc.insert(ignore_permissions=True)
            doc.payload_json = json.dumps(payload, default=str, indent=2)
            doc.save(ignore_permissions=True)
            PluginRegistryService._history(
                None, None, "Export", None, {"profile": profile_name}
            )
        return payload

    @classmethod
    def import_settings(cls, payload: dict[str, Any]) -> dict[str, Any]:
        assert_can_write_settings("apps")
        apps = payload.get("applications") or {}
        updated = 0
        for app_key, sections in apps.items():
            if not isinstance(sections, dict):
                continue
            for section_key, data in sections.items():
                if not isinstance(data, dict):
                    continue
                try:
                    cls.update_settings(app_key, section_key, data)
                    updated += 1
                except Exception:
                    logger.exception("import failed %s/%s", app_key, section_key)
        PluginRegistryService._history(None, None, "Import", None, {"updated": updated})
        return {"updated": updated}

    @classmethod
    def get_dashboard(cls) -> dict[str, Any]:
        from zatgo_core.services.health_service import HealthService

        all_apps = []
        if frappe.db.exists("DocType", APP_DT):
            all_apps = frappe.get_all(
                APP_DT,
                fields=["app_key", "enabled", "visible", "title"],
                limit_page_length=500,
            )
        visible = PluginRegistryService.list_applications()
        enabled = [a for a in all_apps if a.get("enabled")]
        disabled = [a for a in all_apps if not a.get("enabled")]
        pending = 0
        for app in visible:
            full = PluginRegistryService.get_application(app["app_key"])
            if not full:
                continue
            pending += sum(
                1
                for s in (full.get("sections") or [])
                if s.get("component") == "pending"
            )
        health = {}
        try:
            health = HealthService.get_system_health()
        except Exception:
            health = {}
        recent = []
        if frappe.db.exists("DocType", DOCTYPES["CONFIG_HISTORY"]):
            recent = frappe.get_all(
                DOCTYPES["CONFIG_HISTORY"],
                fields=["name", "application", "section_key", "action", "changed_by", "changed_on"],
                order_by="creation desc",
                limit_page_length=10,
            )
        return {
            "installed_apps": len(all_apps),
            "enabled_apps": len(enabled),
            "disabled_apps": len(disabled),
            "visible_to_user": len(visible),
            "pending_configuration": pending,
            "applications": visible,
            "health": health,
            "recent_changes": recent,
            "version": __version__,
        }

    @classmethod
    def _resolve_host(cls, section: dict[str, Any]) -> dict[str, Any]:
        if section.get("link_doctype"):
            return {"type": "doctype", "doctype": section["link_doctype"]}
        component = section.get("component") or "pending"
        return {"type": "component", "component": component}

    @classmethod
    def _load_data(cls, section: dict[str, Any], host: dict[str, Any]) -> Any:
        if host["type"] == "doctype" and host.get("doctype"):
            dt = host["doctype"]
            if not frappe.db.exists("DocType", dt):
                return {"error": f"DocType {dt} missing"}
            meta = frappe.get_meta(dt)
            if meta.issingle:
                return SettingsRepository.get_single(dt).as_dict()
            return {
                "doctype": dt,
                "mode": "list",
                "count": frappe.db.count(dt),
            }
        if host.get("component") == "module_preferences":
            stored = cls._load_component_state(
                section["application"], section["section_key"]
            )
            defaults = {}
            if section.get("defaults_json"):
                try:
                    defaults = json.loads(section["defaults_json"])
                except json.JSONDecodeError:
                    defaults = {}
            return {**defaults, **stored}
        if host.get("component") == "about":
            app = frappe.get_doc(APP_DT, section["application"])
            return {
                "title": app.title,
                "version": app.version,
                "description": app.description,
                "app_key": app.app_key,
            }
        return {"status": "pending", "message": section.get("description") or "Coming soon"}

    @classmethod
    def _component_cache_key(cls, app_key: str, section_key: str) -> str:
        return f"zg_core:component:{app_key}:{section_key}"

    @classmethod
    def _load_component_state(cls, app_key: str, section_key: str) -> dict[str, Any]:
        raw = frappe.cache().get_value(cls._component_cache_key(app_key, section_key))
        if isinstance(raw, dict):
            return raw
        # Persist in defaults_json overlay via site config? Use cache + DB comment field
        name = frappe.db.exists(
            SECTION_DT, {"application": app_key, "section_key": section_key}
        )
        if not name:
            return {}
        doc = frappe.get_doc(SECTION_DT, name)
        # Store live values in a sibling key inside defaults — use frappe.db.set_value on a JSON field
        # We keep runtime state in Redis; also mirror into Config Profile-less site storage via defaults_json merge key "_state"
        if not doc.defaults_json:
            return {}
        try:
            data = json.loads(doc.defaults_json)
        except json.JSONDecodeError:
            return {}
        state = data.get("_state")
        return state if isinstance(state, dict) else {}

    @classmethod
    def _save_component_state(
        cls, app_key: str, section_key: str, values: dict[str, Any]
    ) -> None:
        name = frappe.db.exists(
            SECTION_DT, {"application": app_key, "section_key": section_key}
        )
        if not name:
            frappe.throw(frappe._("Section not found"))
        doc = frappe.get_doc(SECTION_DT, name)
        try:
            data = json.loads(doc.defaults_json) if doc.defaults_json else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data["_state"] = values
        doc.defaults_json = json.dumps(data)
        doc.save(ignore_permissions=True)
        frappe.cache().set_value(
            cls._component_cache_key(app_key, section_key), values, expires_in_sec=3600
        )
