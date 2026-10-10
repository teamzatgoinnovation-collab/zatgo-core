"""Chat AI / Tracker / ZatGo Space are modules of zatgo_core now, but must do
nothing on a site that hasn't switched them on (services/bundled_apps.py) --
zatgo_core runs on every accounting / van-sale site."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.services import bundled_apps

SETTINGS = "ZG System Settings"
FIELDS = ("enable_chat_ai", "enable_tracker", "enable_zatgo_space")


class TestBundledApps(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self._before = {f: frappe.db.get_single_value(SETTINGS, f) for f in FIELDS}
        self._set()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for f, v in self._before.items():
            frappe.db.set_single_value(SETTINGS, f, v or 0)
        frappe.clear_document_cache(SETTINGS, SETTINGS)

    def _set(self, **values: int) -> None:
        for f in FIELDS:
            frappe.db.set_single_value(SETTINGS, f, values.get(f, 0))
        frappe.clear_document_cache(SETTINGS, SETTINGS)

    def test_chat_ai_hooks_do_nothing_where_switched_off(self) -> None:
        doc = frappe._dict(doctype="Sales Invoice", name="X")
        with patch("zatgo_core.chat_ai.erpnext.events.document_events.on_update") as on_update, patch(
            "zatgo_core.chat_ai.erpnext.events.scheduler_events.hourly"
        ) as hourly:
            bundled_apps.chat_ai_on_update(doc)
            bundled_apps.chat_ai_hourly()
            on_update.assert_not_called()
            hourly.assert_not_called()

            self._set(enable_chat_ai=1)
            bundled_apps.chat_ai_on_update(doc)
            bundled_apps.chat_ai_hourly()
            on_update.assert_called_once()
            hourly.assert_called_once()

    def test_tracker_permissions_have_no_say_where_switched_off(self) -> None:
        self.assertEqual(bundled_apps.tracker_project_query("someone@example.com"), "")
        self.assertEqual(bundled_apps.tracker_task_query("someone@example.com"), "")
        self.assertIsNone(bundled_apps.tracker_task_has_permission(frappe._dict(), "someone@example.com"))
        with patch(
            "zatgo_core.tracker.permissions.queries.project_permission_query", return_value="1=0"
        ) as query:
            self._set(enable_tracker=1)
            self.assertEqual(bundled_apps.tracker_project_query("someone@example.com"), "1=0")
            query.assert_called_once()

    def test_desk_assets_only_where_switched_on(self) -> None:
        from zatgo_core.services.ui_apps import desk_includes

        css, js = desk_includes()
        self.assertFalse([u for u in css + js if "/chat_ai/" in u or "/tracker/" in u])
        self._set(enable_tracker=1)
        css, js = desk_includes()
        self.assertTrue(any("/assets/zatgo_core/tracker/js/tracker.js" in u for u in js))
        self.assertFalse(any("/chat_ai/" in u for u in js))

    def test_switched_off_module_has_no_desk_entries(self) -> None:
        bundled_apps.sync_bundled_apps()
        for name in ("AI Admin", "Chat AI", "Tracker"):
            self.assertFalse(frappe.db.exists("Workspace", name), name)
        self.assertFalse(
            frappe.get_all("Desktop Icon", filters={"link_to": ["in", ["AI Admin", "Chat AI", "Tracker"]]})
        )

    def test_module_defs_belong_to_zatgo_core(self) -> None:
        for _key, (_folder, module, _names) in bundled_apps.BUNDLED.items():
            self.assertEqual(frappe.db.get_value("Module Def", module, "app_name"), "zatgo_core", module)
