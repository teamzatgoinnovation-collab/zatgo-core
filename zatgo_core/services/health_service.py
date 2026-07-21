"""System health metrics for dashboards."""

from __future__ import annotations

from typing import Any

import frappe

from zatgo_core.constants.settings import DOCTYPES
from zatgo_core.permissions.guards import assert_can_read_settings


class HealthService:
    """Collect lightweight health indicators for the platform hub."""

    @staticmethod
    def get_system_health() -> dict[str, Any]:
        assert_can_read_settings("system")
        installed_apps = frappe.get_installed_apps()
        redis_ok = True
        try:
            frappe.cache().ping()
        except Exception:
            redis_ok = False

        queue_depth = 0
        try:
            from frappe.utils.background_jobs import get_queue

            for qname in ("default", "short", "long"):
                try:
                    queue_depth += len(get_queue(qname))
                except Exception:
                    continue
        except Exception:
            queue_depth = -1

        users_online = 0
        try:
            users_online = len(frappe.db.sql(
                """
                select distinct user
                from `tabSessions`
                where lastupdate > DATE_SUB(NOW(), INTERVAL 30 MINUTE)
                """
            ))
        except Exception:
            users_online = 0

        return {
            "installed_apps_count": len(installed_apps),
            "installed_apps": installed_apps,
            "redis_ok": redis_ok,
            "queue_depth": queue_depth,
            "users_online": users_online,
            "feature_flags": frappe.db.count(DOCTYPES["FEATURE_FLAG"]),
            "audit_logs": frappe.db.count(DOCTYPES["AUDIT_LOG"]),
            "client_apps": len(
                frappe.get_single(DOCTYPES["APPLICATION_SETTINGS"]).get("client_apps")
                or []
            )
            if frappe.db.exists("DocType", DOCTYPES["APPLICATION_SETTINGS"])
            else 0,
        }
