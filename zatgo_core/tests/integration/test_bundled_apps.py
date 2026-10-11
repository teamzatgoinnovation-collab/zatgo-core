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

    def _user(self, *roles: str) -> str:
        from frappe.utils import random_string

        email = f"bundled.test.{random_string(6).lower()}@zatgo.test"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Bundled",
                "send_welcome_email": 0,
                "roles": [{"role": r} for r in roles],
            }
        ).insert(ignore_permissions=True)
        return email

    def test_tracker_off_leaves_erpnext_project_permissions_alone(self) -> None:
        # Regression: the wrappers returned None when off, which Frappe's
        # has_controller_permissions reads as a DENIAL -- every user but
        # Administrator lost Project / Task / Issue / Timesheet.
        from frappe.utils import random_string

        from zatgo_core.tests.integration._fixtures import get_or_create_test_company

        project = frappe.get_doc(
            {
                "doctype": "Project",
                "project_name": f"Bundled Test {random_string(6)}",
                "company": get_or_create_test_company(),
            }
        ).insert(ignore_permissions=True)
        user = self._user("Projects User", "Projects Manager")
        self.assertTrue(frappe.has_permission("Project", "read", doc=project, user=user))
        self.assertTrue(frappe.has_permission("Project", "write", doc=project, user=user))
        self.assertEqual(bundled_apps.tracker_project_query(user), "")
        with patch(
            "zatgo_core.tracker.permissions.queries.project_permission_query", return_value="1=0"
        ) as query:
            self._set(enable_tracker=1)
            self.assertEqual(bundled_apps.tracker_project_query(user), "1=0")
            query.assert_called_once()

    def test_module_doctypes_are_nobodys_where_switched_off(self) -> None:
        user = self._user("System Manager", "Chat AI Manager")
        self.assertFalse(frappe.has_permission("Chat AI Settings", "read", doc=frappe.get_single("Chat AI Settings"), user=user))
        self.assertEqual(bundled_apps.module_query_conditions(user, doctype="AI Chat Session"), "1=0")
        self.assertEqual(bundled_apps.module_query_conditions(user, doctype="Sales Invoice"), "")
        self.assertTrue(bundled_apps.module_doc_has_permission(frappe._dict(doctype="Sales Invoice")))
        self._set(enable_chat_ai=1)
        self.assertEqual(bundled_apps.module_query_conditions(user, doctype="AI Chat Session"), "")
        self.assertTrue(bundled_apps.module_doc_has_permission(frappe._dict(doctype="AI Chat Session")))

    def _call_gate(self, path: str) -> None:
        had = hasattr(frappe.local, "request")
        orig = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict(path=path)
            bundled_apps.gate_module_api()
        finally:
            if had:
                frappe.local.request = orig
            else:
                del frappe.local.request

    def test_module_api_is_404_where_switched_off(self) -> None:
        for path in (
            "/api/method/zatgo_core.zatgo_space.api.v1.space.list_catalog",
            "/api/v2/method/zatgo_space.api.v1.space.list_catalog",  # old app path
            "/api/method/zatgo_core.chat_ai.api.chat.send",
            "/api/method/tracker.api.v1.hierarchy.org_tree",
        ):
            with self.assertRaises(frappe.DoesNotExistError, msg=path):
                self._call_gate(path)
        self._call_gate("/api/method/zatgo_core.api.v1.vansalex.me.context")  # not a module
        self._call_gate("/desk/sales-invoice")
        self._set(enable_zatgo_space=1)
        self._call_gate("/api/method/zatgo_core.zatgo_space.api.v1.space.list_catalog")

    def test_old_method_paths_map_to_the_merged_modules(self) -> None:
        from zatgo_core.compat_methods import OLD_METHOD_PATHS

        self.assertEqual(
            OLD_METHOD_PATHS["tracker.api.v1.tasks.list_tasks"], "zatgo_core.tracker.api.v1.tasks.list_tasks"
        )
        for new in OLD_METHOD_PATHS.values():
            self.assertTrue(callable(frappe.get_attr(new)), new)

    def test_status_brief_refuses_a_company_the_user_cannot_read(self) -> None:
        from zatgo_core.chat_ai.erpnext.skills.analytics import tools

        self._set(enable_chat_ai=1)
        with patch.object(frappe, "has_permission", return_value=False):
            with self.assertRaises(frappe.PermissionError):
                tools._company_status_brief(company="Some Other Company")

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
