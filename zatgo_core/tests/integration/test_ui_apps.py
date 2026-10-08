"""The theme, language switcher and VanSaleX web page that used to be
separate apps, now switched per site in ZG System Settings
(services/ui_apps.py, patches/v0_2_9/carry_over_ui_apps.py)."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.services import ui_apps

SETTINGS = "ZG System Settings"
FIELDS = ("enable_saas_theme", "enable_language_switcher", "enable_vansalex_web")


class TestUiApps(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self._before = {f: frappe.db.get_single_value(SETTINGS, f) for f in FIELDS}

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for f, v in self._before.items():
            frappe.db.set_single_value(SETTINGS, f, v or 0)
        frappe.clear_document_cache(SETTINGS, SETTINGS)

    def _set(self, **values: int) -> None:
        for f in FIELDS:
            frappe.db.set_single_value(SETTINGS, f, values.get(f, 0))
        frappe.clear_document_cache(SETTINGS, SETTINGS)

    # -- Desk includes ---------------------------------------------------------

    def test_desk_includes_follow_the_switches(self) -> None:
        self._set()
        self.assertEqual(ui_apps.desk_includes(), ([], []))
        self._set(enable_saas_theme=1)
        css, js = ui_apps.desk_includes()
        self.assertTrue(css[0].startswith("/assets/zatgo_core/saas_theme/css/saas_theme.css?v="))
        self.assertTrue(js[0].startswith("/assets/zatgo_core/saas_theme/js/saas_theme.js?v="))
        self._set(enable_language_switcher=1)
        css, js = ui_apps.desk_includes()
        self.assertEqual(len(css), 1)
        self.assertIn("language_switcher", js[0])

    def test_add_desk_includes_only_on_desk_and_never_mutates_shared_lists(self) -> None:
        self._set(enable_saas_theme=1)
        shared = ["/assets/x/site.css"]
        conf = frappe._dict(app_include_css=shared)
        # frappe.local is a werkzeug Local: set/restore by hand (mock.patch
        # would delete the attribute on exit).
        orig_conf = frappe.local.conf
        had_request = hasattr(frappe.local, "request")
        orig_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.conf = conf
            frappe.local.request = frappe._dict(path="/api/method/ping")
            ui_apps.add_desk_includes()
            self.assertIs(conf.app_include_css, shared)
            frappe.local.request = frappe._dict(path="/desk/sales-invoice")
            ui_apps.add_desk_includes()
        finally:
            frappe.local.conf = orig_conf
            if had_request:
                frappe.local.request = orig_request
            else:
                del frappe.local.request
        self.assertEqual(shared, ["/assets/x/site.css"], "the cached list must stay untouched")
        self.assertEqual(conf.app_include_css[0], "/assets/x/site.css")
        self.assertIn("saas_theme.css", conf.app_include_css[1])
        self.assertIn("saas_theme.js", conf.app_include_js[0])

    # -- Login page ------------------------------------------------------------

    def test_themed_login_only_claims_login_while_the_theme_is_on(self) -> None:
        self._set()
        self.assertFalse(ui_apps.ThemedLoginPage("login").can_render())
        self._set(enable_saas_theme=1)
        self.assertTrue(ui_apps.ThemedLoginPage("login").can_render())
        self.assertFalse(ui_apps.ThemedLoginPage("about").can_render())

    def test_login_page_is_themed_only_where_switched_on(self) -> None:
        from frappe.utils import set_request
        from frappe.website.serve import get_response

        frappe.set_user("Guest")
        try:
            self._set(enable_saas_theme=1)
            set_request(method="GET", path="/login")
            html = get_response("login").get_data(as_text=True)
            self.assertIn("/assets/zatgo_core/saas_theme/css/login.css", html)
            self.assertIn('id="login_email"', html)

            self._set()
            set_request(method="GET", path="/login")
            html = get_response("login").get_data(as_text=True)
            self.assertNotIn("saas_theme", html)
            self.assertIn('id="login_email"', html)
        finally:
            frappe.set_user("Administrator")

    # -- VanSaleX web page -----------------------------------------------------

    def test_vansalex_page_is_404_where_switched_off(self) -> None:
        from zatgo_core.www import vansalex

        self._set()
        with self.assertRaises(frappe.PageDoesNotExistError):
            vansalex.get_context(frappe._dict())
        self._set(enable_vansalex_web=1)
        self.assertIsNotNone(vansalex.get_context(frappe._dict()))

    # -- Language API ----------------------------------------------------------

    def test_set_language_changes_only_the_callers_own_language(self) -> None:
        from zatgo_core.api.v1.language import set_language

        before = frappe.db.get_value("User", "Administrator", "language")
        try:
            self.assertEqual(set_language("ar"), {"language": "ar"})
            self.assertEqual(frappe.db.get_value("User", "Administrator", "language"), "ar")
            with self.assertRaises(frappe.ValidationError):
                set_language("fr")
            frappe.set_user("Guest")
            with self.assertRaises(frappe.PermissionError):
                set_language("en")
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("User", "Administrator", "language", before)

    # -- Carry-over patch ------------------------------------------------------

    def test_patch_switches_on_what_was_installed(self) -> None:
        from zatgo_core.patches.v0_2_9 import carry_over_ui_apps

        self._set()
        with patch.object(frappe, "get_installed_apps", return_value=["frappe", "erpnext", "zatgo_core", "modifyme"]):
            carry_over_ui_apps.execute()
        self.assertEqual(
            [frappe.db.get_single_value(SETTINGS, f) for f in FIELDS], [0, 1, 0],
        )
        with patch.object(
            frappe, "get_installed_apps", return_value=["frappe", "erpnext", "zatgo_core", "saas_theme", "vansalex_web"]
        ):
            carry_over_ui_apps.execute()
        self.assertEqual(
            [frappe.db.get_single_value(SETTINGS, f) for f in FIELDS], [1, 1, 1],
        )
