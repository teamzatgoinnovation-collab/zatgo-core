"""ZatGo app switches end to end: VanSaleX is a switchable app (on unless switched off), only a System Manager
can switch, the registry mirrors the switches, and the config / per-user DocTypes are guarded server-side.

Runs against a real site (switches are flipped and restored per test)."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core import __version__
from zatgo_core.api.v1 import app_hub
from zatgo_core.plugins.discover import discover_and_register_manifests
from zatgo_core.services import app_catalog, app_gate, app_sidebar, app_state, core_sidebar

SETTINGS = "ZG System Settings"
SWITCH_FIELDS = ("enable_vansalex", "enable_vansalex_web", "enable_tracker", "enable_language_switcher")
VANSALEX_WORKSPACE = "ZatGo VanSaleX"
VANSALEX_METHOD = "/api/method/zatgo_core.api.v1.vansalex.me.context"


def _make_user(*roles: str) -> str:
    email = f"switches.{random_string(8).lower()}@zatgo.test"
    frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": "Switches",
            "send_welcome_email": 0,
            "roles": [{"role": r} for r in roles],
        }
    ).insert(ignore_permissions=True)
    return email


def _store(field: str, value) -> None:
    """Write (or, with None, remove) the stored value of a ZG System Settings field."""
    if value is None:
        frappe.db.delete("Singles", {"doctype": SETTINGS, "field": field})
    else:
        frappe.db.set_single_value(SETTINGS, field, value)
    frappe.clear_document_cache(SETTINGS, SETTINGS)


def _stored(field: str):
    rows = frappe.db.sql("select value from `tabSingles` where doctype = %s and field = %s", (SETTINGS, field))
    return rows[0][0] if rows else None


class AppSwitchTestCase(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self._before = {f: _stored(f) for f in SWITCH_FIELDS}

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for field, value in self._before.items():
            _store(field, value)
        # Put the Desk entries and the sidebar back to the restored switches.
        from zatgo_core.services.app_desk import sync_app_desk

        sync_app_desk()
        core_sidebar.sync_core_sidebar()
        app_sidebar.sync_app_sidebars()
        frappe.db.commit()

    def _gate(self, path: str) -> None:
        had = hasattr(frappe.local, "request")
        orig = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict(path=path)
            app_gate.gate_api()
        finally:
            if had:
                frappe.local.request = orig
            else:
                del frappe.local.request


class TestVanSaleXSwitch(AppSwitchTestCase):
    def test_vansalex_is_a_switchable_app_that_is_on_by_default(self) -> None:
        app = app_catalog.get("vansalex")
        self.assertEqual(app["switch_field"], "enable_vansalex")
        self.assertTrue(app["default_on"])
        self.assertEqual(app["group"], "app")
        self.assertTrue(frappe.get_meta(SETTINGS).has_field("enable_vansalex"))
        # No stored value (a site that has not migrated): still on.
        _store("enable_vansalex", None)
        self.assertTrue(app_state.is_on("vansalex"))
        # An explicit 0 is off; an app without a switch stays on.
        _store("enable_vansalex", 0)
        self.assertFalse(app_state.is_on("vansalex"))
        self.assertTrue(app_state.is_on("core_settings"))

    def test_the_patch_stores_the_default_and_leaves_an_explicit_off_alone(self) -> None:
        from zatgo_core.patches.v0_4_7 import enable_vansalex_default_on

        _store("enable_vansalex", None)
        enable_vansalex_default_on.execute()
        self.assertEqual(_stored("enable_vansalex"), "1")
        _store("enable_vansalex", 0)
        enable_vansalex_default_on.execute()
        self.assertEqual(_stored("enable_vansalex"), "0")

    def test_off_answers_404_for_its_api_only_and_on_brings_it_back(self) -> None:
        _store("enable_vansalex", 1)
        self._gate(VANSALEX_METHOD)
        _store("enable_vansalex", 0)
        with self.assertRaises(frappe.DoesNotExistError):
            self._gate(VANSALEX_METHOD)
        # Shared endpoints other clients use are not VanSaleX's.
        self._gate("/api/method/zatgo_core.api.v1.accounting.dashboard.get_dashboard")
        self._gate("/desk/sales-invoice")
        _store("enable_vansalex", 1)
        self._gate(VANSALEX_METHOD)

    def test_switching_off_hides_the_desk_entries_and_keeps_the_data(self) -> None:
        if not frappe.db.exists("Workspace", VANSALEX_WORKSPACE):
            self.skipTest("the VanSaleX workspace is not synced on this site")
        settings_before = frappe.get_single("VanSaleX Settings").as_dict()
        app_hub.set_switch("vansalex", 0)
        self.assertEqual(frappe.db.get_value("Workspace", VANSALEX_WORKSPACE, "is_hidden"), 1)
        for icon in frappe.get_all("Desktop Icon", filters={"link_to": VANSALEX_WORKSPACE}, pluck="hidden"):
            self.assertEqual(int(icon), 1)
        # Its own sidebar keeps no items while off (Frappe then leaves it out), and the ZatGo one never listed it.
        self.assertFalse(frappe.get_doc("Workspace Sidebar", VANSALEX_WORKSPACE).items)
        after = frappe.get_single("VanSaleX Settings").as_dict()
        for key in ("default_payment_type", "allow_credit_sales", "max_discount_percent", "config_version"):
            self.assertEqual(after.get(key), settings_before.get(key), key)

        app_hub.set_switch("vansalex", 1)
        self.assertEqual(frappe.db.get_value("Workspace", VANSALEX_WORKSPACE, "is_hidden"), 0)
        items = frappe.get_doc("Workspace Sidebar", VANSALEX_WORKSPACE).items
        self.assertEqual(items[0].label, "Overview")
        # Apps open from ZatGo > Apps: switching the app on does not bring its own rail icon back.
        for icon in frappe.get_all("Desktop Icon", filters={"link_to": VANSALEX_WORKSPACE}, pluck="hidden"):
            self.assertEqual(int(icon), 1)

    def test_a_migrate_that_resyncs_the_workspace_is_followed_by_hiding_it_again(self) -> None:
        """Migrate re-imports the synced workspace file (visible); `ensure_ui_apps` then hides it again."""
        if not frappe.db.exists("Workspace", VANSALEX_WORKSPACE):
            self.skipTest("the VanSaleX workspace is not synced on this site")
        from zatgo_core.services.app_desk import sync_app_desk

        app_hub.set_switch("vansalex", 0)
        frappe.db.set_value("Workspace", VANSALEX_WORKSPACE, "is_hidden", 0)  # what the re-import does
        self.assertTrue(sync_app_desk())
        self.assertEqual(frappe.db.get_value("Workspace", VANSALEX_WORKSPACE, "is_hidden"), 1)
        self.assertFalse(sync_app_desk(), "nothing left to change")

    def test_the_web_page_needs_the_app(self) -> None:
        """/vansalex is the VanSaleX app's page: it follows the app, and the pair cannot be saved in a state
        where the page is on and the app off."""
        _store("enable_vansalex_web", 1)
        _store("enable_vansalex", 1)
        doc = frappe.get_doc(SETTINGS)
        doc.enable_vansalex = 0
        with self.assertRaises(frappe.ValidationError):
            doc.save()
        _store("enable_vansalex_web", 0)
        doc = frappe.get_doc(SETTINGS)
        doc.enable_vansalex = 0
        doc.save()  # nothing needs it any more
        self.assertFalse(app_state.is_on("vansalex"))


class TestSwitchAuthority(AppSwitchTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.company_admin = _make_user("ZG Company Admin")
        cls.app_admin = _make_user("ZG Application Admin")
        cls.manager = _make_user("System Manager")

    def _flip_as(self, user: str, field: str = "enable_tracker"):
        frappe.set_user(user)
        doc = frappe.get_doc(SETTINGS)
        doc.set(field, 0 if doc.get(field) else 1)
        doc.save()

    def test_company_admin_and_application_admin_cannot_flip_a_switch(self) -> None:
        for user in (self.company_admin, self.app_admin):
            with self.assertRaises(frappe.PermissionError, msg=user):
                self._flip_as(user)
            frappe.set_user("Administrator")
            self.assertEqual(_stored("enable_tracker"), self._before["enable_tracker"], "nothing was written")

    def test_nor_can_they_switch_an_industry(self) -> None:
        frappe.set_user(self.company_admin)
        doc = frappe.get_doc(SETTINGS)
        from zatgo_core.industries.sync import ensure_rows

        ensure_rows(doc)
        row = next(r for r in doc.enabled_industries if r.industry == "gym")
        row.enabled = 0 if row.enabled else 1
        with self.assertRaises(frappe.PermissionError):
            doc.save()

    def test_they_can_still_save_the_other_settings(self) -> None:
        frappe.set_user(self.company_admin)
        doc = frappe.get_doc(SETTINGS)
        original = doc.brand_name
        doc.brand_name = f"{original or 'ZatGo'} "
        try:
            doc.save()  # a change that is not a switch is not held against them
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_single_value(SETTINGS, "brand_name", original)

    def test_a_system_manager_can(self) -> None:
        self._flip_as(self.manager)
        frappe.set_user("Administrator")
        self.assertNotEqual(_stored("enable_tracker"), self._before["enable_tracker"])

    def test_the_hub_agrees(self) -> None:
        for user in (self.company_admin, self.app_admin):
            frappe.set_user(user)
            self.assertFalse(app_hub.get_hub()["success"])
            self.assertFalse(app_hub.set_switch("tracker", 1)["success"])
        frappe.set_user(self.manager)
        self.assertTrue(app_hub.get_hub()["success"])

    def test_install_and_migrate_are_not_a_user(self) -> None:
        frappe.set_user(self.company_admin)
        doc = frappe.get_doc(SETTINGS)
        doc.enable_tracker = 0 if doc.enable_tracker else 1
        frappe.flags.in_migrate = True
        try:
            doc.save()
        finally:
            frappe.flags.in_migrate = False


class TestHubPayload(AppSwitchTestCase):
    def test_summary_counts_come_from_the_rows_shown(self) -> None:
        data = app_hub.get_hub()["data"]
        self.assertEqual(data["version"], __version__)
        self.assertTrue(data["css"].startswith("/assets/zatgo_core/css/zg_app_hub.css?v="))
        self.assertEqual(data["load_errors"], [])
        switchable = [a for a in data["apps"] if a["has_switch"]]
        self.assertEqual(data["summary"]["apps"], len(data["apps"]))
        self.assertEqual(data["summary"]["enabled"] + data["summary"]["disabled"], len(switchable))
        self.assertEqual(data["summary"]["enabled"], sum(1 for a in switchable if a["enabled"]))
        self.assertEqual(data["summary"]["warnings"], sum(len(a["warnings"]) for a in data["apps"]))
        by_key = {a["key"]: a for a in data["apps"]}
        self.assertTrue(by_key["vansalex"]["has_switch"])
        self.assertEqual(by_key["vansalex_web"]["requires"], ["ZatGo VanSaleX"])
        self.assertEqual(by_key["vansalex"]["version"], __version__)
        self.assertFalse(by_key["core_settings"]["has_switch"])

    def test_an_app_that_is_off_reports_no_warnings(self) -> None:
        _store("enable_tracker", 0)
        by_key = {a["key"]: a for a in app_hub.get_hub()["data"]["apps"]}
        self.assertFalse(by_key["tracker"]["enabled"])
        self.assertEqual(by_key["tracker"]["warnings"], [])

    def test_a_dependent_app_that_is_on_while_its_requirement_is_off_is_reported(self) -> None:
        _store("enable_vansalex", 0)
        _store("enable_vansalex_web", 1)  # a state the form refuses, reached the way a migrate could
        by_key = {a["key"]: a for a in app_hub.get_hub()["data"]["apps"]}
        self.assertTrue(any("ZatGo VanSaleX" in w for w in by_key["vansalex_web"]["warnings"]))

    def test_turning_the_language_switcher_on_enables_arabic_at_once(self) -> None:
        if not frappe.db.exists("Language", "ar"):
            self.skipTest("no Arabic Language record on this site")
        was = frappe.db.get_value("Language", "ar", "enabled")
        try:
            _store("enable_language_switcher", 0)
            frappe.db.set_value("Language", "ar", "enabled", 0)
            app_hub.set_switch("language_switcher", 1)
            self.assertEqual(frappe.db.get_value("Language", "ar", "enabled"), 1)
        finally:
            frappe.db.set_value("Language", "ar", "enabled", was)


class TestRegistryMirrorsSwitches(AppSwitchTestCase):
    def _row(self, key: str):
        return frappe.get_doc("ZG Registered Application", key)

    def test_catalog_entries_register_with_valid_values_and_the_real_state(self) -> None:
        _store("enable_tracker", 1)
        result = discover_and_register_manifests()
        self.assertGreaterEqual(result["registered"], 8)  # was: the 5 catalog-derived ones failed validation
        tracker = self._row("tracker")
        self.assertEqual(tracker.category, "Other")
        self.assertEqual(tracker.version, __version__)
        self.assertEqual(tracker.enabled, 1)
        self.assertEqual(self._row("core_settings").category, "Platform")
        _store("enable_tracker", 0)
        discover_and_register_manifests()
        self.assertEqual(self._row("tracker").enabled, 0)

    def test_vansalex_has_one_registry_entry_named_like_the_app(self) -> None:
        discover_and_register_manifests()
        row = self._row("vansalex")
        self.assertEqual(row.title, "ZatGo VanSaleX")
        self.assertEqual(row.version, __version__)
        sections = {s.section_key for s in frappe.get_all("ZG Setting Section", filters={"application": "vansalex"}, fields=["section_key"])}
        self.assertTrue({"general", "profiles", "payments"} <= sections)

    def test_a_second_run_changes_nothing_and_writes_no_history(self) -> None:
        discover_and_register_manifests()
        history = frappe.db.count("ZG Config History", {"action": "Register"})
        again = discover_and_register_manifests()
        self.assertEqual(again["changed"], 0)
        self.assertEqual(frappe.db.count("ZG Config History", {"action": "Register"}), history)

    def test_an_admins_edit_survives_a_migrate_but_the_switch_stays_the_truth(self) -> None:
        discover_and_register_manifests()
        original_visible = self._row("delivery").visible
        original_enabled = self._row("tracker").enabled
        try:
            frappe.db.set_value("ZG Registered Application", "delivery", "visible", 0 if original_visible else 1)
            _store("enable_tracker", 1)
            frappe.db.set_value("ZG Registered Application", "tracker", "enabled", 0)
            discover_and_register_manifests()
            self.assertEqual(self._row("delivery").visible, 0 if original_visible else 1, "the admin's choice is kept")
            self.assertEqual(self._row("tracker").enabled, 1, "the site's switch wins over a stray edit")
        finally:
            frappe.db.set_value("ZG Registered Application", "delivery", "visible", original_visible)
            frappe.db.set_value("ZG Registered Application", "tracker", "enabled", original_enabled)


class TestAppApiDecorator(AppSwitchTestCase):
    """`@app_api(key)` under `@frappe.whitelist()`: login + app on (+ roles) before the function runs."""

    def _endpoint(self, **kw):
        @app_gate.app_api("vansalex", **kw)
        def endpoint():
            return "ran"

        return endpoint

    def test_guest_app_off_and_wrong_role_are_refused_before_the_function_runs(self) -> None:
        endpoint = self._endpoint()
        frappe.set_user("Guest")
        with self.assertRaises(frappe.AuthenticationError):
            endpoint()
        frappe.set_user("Administrator")
        self.assertEqual(endpoint(), "ran")
        _store("enable_vansalex", 0)
        with self.assertRaises(frappe.PermissionError):
            endpoint()
        _store("enable_vansalex", 1)
        user = _make_user("Sales User")
        frappe.set_user(user)
        self.assertEqual(endpoint(), "ran")
        with self.assertRaises(frappe.PermissionError):
            self._endpoint(roles=("VanSale Admin",))()

    def test_require_app_names_the_app(self) -> None:
        _store("enable_vansalex", 0)
        with self.assertRaises(frappe.PermissionError) as ctx:
            app_gate.require_app("vansalex")
        self.assertIn("ZatGo VanSaleX", str(ctx.exception))


class TestClientAppFlag(AppSwitchTestCase):
    def test_a_client_product_of_a_switched_off_app_is_not_enabled(self) -> None:
        from zatgo_core.services.app_registry_service import AppRegistryService

        AppRegistryService.seed_default_client_apps(replace=False)
        _store("enable_tracker", 0)
        self.assertFalse(AppRegistryService.is_client_enabled("tracker"))
        _store("enable_tracker", 1)
        row = AppRegistryService.get_client_app("tracker")
        self.assertEqual(AppRegistryService.is_client_enabled("tracker"), bool(row and row.get("enabled")))
