"""Licensing registry against a real site: every name it maps exists, the projection is idempotent and read-only."""

from __future__ import annotations

import json

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.licensing import registry
from zatgo_core.licensing.sync import FEATURE_DOCTYPE, MODULE_DOCTYPE, sync_registry
from zatgo_core.services import app_catalog


class TestLicensingRegistryOnSite(IntegrationTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_registry()
        cls.installed = set(frappe.get_installed_apps())

    def tearDown(self) -> None:
        frappe.set_user("Administrator")

    def _live(self):
        return [f for f in registry.features() if f.source_app in self.installed and not f.retired]

    # -- every mapped name exists -----------------------------------------------------------------------------

    def test_mapped_doctypes_exist_are_not_child_tables_and_fit_their_actions(self) -> None:
        problems = []
        for f in self._live():
            for g in f.doctypes:
                if not frappe.db.exists("DocType", g.doctype):
                    problems.append(f"{f.id}: DocType {g.doctype} missing")
                    continue
                meta = frappe.get_meta(g.doctype)
                if meta.istable:
                    problems.append(f"{f.id}: {g.doctype} is a child table")
                if meta.issingle and set(g.actions) - {"read", "write"}:
                    problems.append(f"{f.id}: {g.doctype} is a Single, only read/write apply")
                if not meta.is_submittable and set(g.actions) & {"submit", "cancel", "amend"}:
                    problems.append(f"{f.id}: {g.doctype} is not submittable")
                for field, _value in g.match:
                    if not meta.has_field(field):
                        problems.append(f"{f.id}: {g.doctype} has no field {field}")
        self.assertEqual(problems, [])

    def test_mapped_reports_pages_workspaces_and_api_modules_exist(self) -> None:
        import importlib.util

        problems = []
        for f in self._live():
            for name in f.reports:
                if not frappe.db.exists("Report", name):
                    problems.append(f"{f.id}: Report {name}")
            # A bundled module's Desk records are created by its own setup, not synced: tolerated here like its
            # workspaces (a missing one is that module's problem, not the registry's).
            bundled = bool(f.app_key) and (app_catalog.get(f.app_key) or {}).get("group") == "bundled"
            for name in f.pages:
                if not frappe.db.exists("Page", name) and not bundled:
                    problems.append(f"{f.id}: Page {name}")
            # A bundled app's workspace exists only while the app is switched on (its desk_records); it must
            # then be one the app's manifest owns.
            owned = set(app_catalog.get(f.app_key)["workspaces"]) if f.app_key else set()
            for name in f.workspaces:
                if not frappe.db.exists("Workspace", name) and name not in owned:
                    problems.append(f"{f.id}: Workspace {name}")
            for prefix in f.api_prefixes:
                if importlib.util.find_spec(prefix[:-1]) is None:
                    problems.append(f"{f.id}: API module {prefix}")
        self.assertEqual(problems, [])

    def test_match_values_are_real_options(self) -> None:
        purposes = set(frappe.get_meta("Stock Entry").get_field("purpose").options.split("\n"))
        for f in self._live():
            for g in f.doctypes:
                for field, value in g.match:
                    if g.doctype == "Stock Entry" and field == "purpose":
                        values = value if isinstance(value, tuple) else (value,)
                        self.assertEqual(set(values) - purposes, set(), f.id)

    # -- the projection --------------------------------------------------------------------------------------

    def test_projection_mirrors_the_code(self) -> None:
        self.assertEqual(frappe.db.count(MODULE_DOCTYPE), len(registry.modules()))
        self.assertEqual(frappe.db.count(FEATURE_DOCTYPE, {"retired": 0}),
                         len([f for f in registry.features() if not f.retired]))
        row = frappe.get_doc(FEATURE_DOCTYPE, "sales.return")
        self.assertEqual(row.module, "sales")
        self.assertEqual(json.loads(row.doctype_map)[0]["match"], {"is_return": 1})
        self.assertEqual(json.loads(row.requires), {"sales.invoice": ["read"]})
        self.assertEqual(row.available, 1)
        hr = frappe.db.get_value(FEATURE_DOCTYPE, "hr_payroll.payroll", "available")
        self.assertEqual(hr, int("hrms" in self.installed))

    def test_a_second_sync_writes_nothing(self) -> None:
        self.assertEqual(sync_registry(), {"modules": 0, "features": 0, "retired": 0})

    def test_a_drifted_row_is_put_back(self) -> None:
        frappe.db.set_value(FEATURE_DOCTYPE, "sales.order", "label", "Tampered", update_modified=False)
        written = sync_registry()
        self.assertEqual(written["features"], 1)
        self.assertEqual(frappe.db.get_value(FEATURE_DOCTYPE, "sales.order", "label"), "Sales Orders")

    def test_rows_cannot_be_changed_by_hand(self) -> None:
        doc = frappe.get_doc(FEATURE_DOCTYPE, "sales.invoice")
        doc.label = "Free for everyone"
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)  # even with ignore_permissions: the controller refuses
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({"doctype": FEATURE_DOCTYPE, "feature_id": "sales.free", "label": "x",
                            "module": "sales"}).insert(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc(FEATURE_DOCTYPE, "sales.invoice", ignore_permissions=True)
        self.assertEqual(frappe.db.get_value(FEATURE_DOCTYPE, "sales.invoice", "label"), "Sales Invoices")

    def test_desk_client_save_is_refused_for_a_system_manager(self) -> None:
        user = self._user("System Manager")
        frappe.set_user(user)
        self.assertFalse(frappe.has_permission(FEATURE_DOCTYPE, "write"))
        self.assertFalse(frappe.has_permission(FEATURE_DOCTYPE, "create"))
        from frappe.client import set_value

        with self.assertRaises(frappe.PermissionError):
            set_value(FEATURE_DOCTYPE, "sales.invoice", "label", "x")

    def test_read_only_role_can_read(self) -> None:
        frappe.set_user(self._user("ZatGo Read Only"))
        rows = frappe.get_list(FEATURE_DOCTYPE, filters={"module": "accounting"}, pluck="name")
        self.assertIn("accounting.journal_entry", rows)
        self.assertTrue(frappe.has_permission(MODULE_DOCTYPE, "read"))

    def test_a_user_without_the_roles_cannot_read(self) -> None:
        frappe.set_user(self._user("Sales User"))
        self.assertFalse(frappe.has_permission(FEATURE_DOCTYPE, "read"))

    def _user(self, role: str) -> str:
        email = f"zg-lic-{random_string(8).lower()}@example.com"
        frappe.get_doc({
            "doctype": "User", "email": email, "first_name": "Licensing test", "send_welcome_email": 0,
            "roles": [{"role": role}],
        }).insert(ignore_permissions=True)
        return email
