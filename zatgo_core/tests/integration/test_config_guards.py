"""The config API and the per-user DocTypes are guarded on the server, whatever the client sends
(api/v1/config.py, api/v1/settings.py, permissions/owner_scope.py)."""

from __future__ import annotations

import frappe
from frappe.utils import random_string

from zatgo_core.api.v1 import config, settings as settings_api
from zatgo_core.repositories.settings_repository import SettingsRepository
from zatgo_core.tests.integration.test_app_switches import AppSwitchTestCase, _make_user


class TestConfigApiIsGuarded(AppSwitchTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.sales = _make_user("Sales User")
        cls.read_only = _make_user("ZG Read Only")
        cls.branch_admin = _make_user("ZG Branch Admin")

    def test_registry_reseed_export_and_dashboard_need_a_manager(self) -> None:
        for user in (self.sales, self.read_only):
            frappe.set_user(user)
            with self.assertRaises(frappe.PermissionError, msg=f"seed {user}"):
                config.seed_bundled_manifests()
            with self.assertRaises(frappe.PermissionError, msg=f"export {user}"):
                config.export_settings("leak")
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            config.get_dashboard()
        frappe.set_user("Administrator")
        self.assertTrue(config.seed_bundled_manifests()["success"])
        self.assertTrue(config.get_dashboard()["success"])

    def test_a_caller_cannot_choose_the_rule_that_guards_its_own_write(self) -> None:
        frappe.set_user(self.branch_admin)
        with self.assertRaises(frappe.PermissionError):
            # Claiming the "branch" category must not let a Branch Admin write system settings.
            settings_api.save_settings("ZG System Settings", '{"brand_name": "x"}', category="branch")

    def test_only_zatgo_settings_doctypes_can_be_saved_here(self) -> None:
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            settings_api.save_settings("User", '{"first_name": "x"}', name="Administrator")

    def test_the_config_api_reaches_the_settings_apps_list_but_nothing_else(self) -> None:
        frappe.set_user("Administrator")
        self.assertEqual(SettingsRepository.get_single("VanSaleX Settings").doctype, "VanSaleX Settings")
        with self.assertRaises(frappe.ValidationError):
            SettingsRepository.get_single("System Settings")


class TestPerUserDocTypes(AppSwitchTestCase):
    """Push tokens and preferences belong to their user on every route, REST and Desk included."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.alice = _make_user("Sales User")
        cls.bob = _make_user("Sales User")

    def _token(self, user: str):
        return frappe.get_doc(
            {"doctype": "ZG Device Token", "user": user, "token": f"tok-{random_string(12)}", "platform": "android", "app_id": "t"}
        ).insert(ignore_permissions=True)

    def test_a_user_sees_only_their_own_tokens(self) -> None:
        a, b = self._token(self.alice), self._token(self.bob)
        frappe.set_user(self.alice)
        names = frappe.get_list("ZG Device Token", pluck="name")
        self.assertIn(a.name, names)
        self.assertNotIn(b.name, names)
        self.assertTrue(frappe.has_permission("ZG Device Token", "read", doc=a))
        self.assertFalse(frappe.has_permission("ZG Device Token", "read", doc=b))
        self.assertFalse(frappe.has_permission("ZG Device Token", "write", doc=b))
        frappe.set_user("Administrator")
        self.assertIn(b.name, frappe.get_list("ZG Device Token", pluck="name"), "a System Manager sees all")

    def test_nobody_can_register_a_token_under_someone_else(self) -> None:
        frappe.set_user(self.alice)
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(
                {"doctype": "ZG Device Token", "user": self.bob, "token": f"tok-{random_string(12)}", "platform": "android", "app_id": "t"}
            ).insert()

    def test_preferences_are_private_too(self) -> None:
        mine = SettingsRepository.ensure_user_preferences(self.alice)
        theirs = SettingsRepository.ensure_user_preferences(self.bob)
        frappe.set_user(self.alice)
        self.assertTrue(frappe.has_permission("ZG User Preferences", "read", doc=mine))
        self.assertFalse(frappe.has_permission("ZG User Preferences", "read", doc=theirs))
        self.assertNotIn(theirs.name, frappe.get_list("ZG User Preferences", pluck="name"))
