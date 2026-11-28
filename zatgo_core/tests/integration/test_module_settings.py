"""Module Settings (Phase 5): rows per module, the switching rules, and what switching off does and never does."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.licensing import registry
from zatgo_core.services import app_state, module_settings
from zatgo_core.services.core import availability


def _set(states: dict[str, int]) -> None:
    doc = frappe.get_doc(module_settings.DOCTYPE)
    for row in doc.modules:
        if row.module in states:
            row.enabled = states[row.module]
    doc.save()
    module_settings.after_change()


class TestModuleSettings(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        module_settings.sync_rows()
        self.saved = {r.module: r.enabled for r in frappe.get_doc(module_settings.DOCTYPE).modules}

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        _set(self.saved)
        frappe.db.commit()

    def test_one_row_per_registry_module_and_a_rerun_writes_nothing(self) -> None:
        rows = {r.module for r in frappe.get_doc(module_settings.DOCTYPE).modules}
        self.assertEqual(rows, {m.id for m in registry.modules()})
        self.assertFalse(module_settings.sync_rows(), "a second sync must not save")

    def test_dependencies_come_from_the_registry(self) -> None:
        self.assertIn("sales", module_settings.dependencies()["pos"])
        self.assertNotIn("foundation", module_settings.dependencies()["pos"])

    def test_foundation_cannot_be_switched_off(self) -> None:
        with self.assertRaises(frappe.ValidationError):
            _set({"foundation": 0})

    def test_a_needed_module_cannot_be_switched_off(self) -> None:
        self.assertTrue(module_settings.is_enabled("pos"))
        with self.assertRaises(frappe.ValidationError) as ctx:
            _set({"sales": 0})
        self.assertIn("needed by", str(ctx.exception))

    def test_a_module_cannot_be_switched_on_without_its_needs(self) -> None:
        _set({"pos": 0, "vansalex": 0, "industries": 0, "zatgo_apps": 0, "crm": 0, "service": 0})
        needs_sales = {m for m, needs in module_settings.dependencies().items() if "sales" in needs}
        _set({m: 0 for m in needs_sales})
        _set({"sales": 0})
        with self.assertRaises(frappe.ValidationError) as ctx:
            _set({"pos": 1})
        self.assertIn("needs", str(ctx.exception))

    def test_only_a_system_manager_switches_modules(self) -> None:
        email = f"zg-modules-{random_string(6).lower()}@example.test"
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "m", "send_welcome_email": 0,
                        "roles": [{"role": "ZatGo Application Admin"}]}).insert(ignore_permissions=True)
        try:
            frappe.set_user(email)
            doc = frappe.get_doc(module_settings.DOCTYPE)
            next(r for r in doc.modules if r.module == "service").enabled = 0
            doc.flags.ignore_permissions = True  # past the DocPerm: the controller rule is what is tested
            with self.assertRaises(frappe.PermissionError):
                doc.save()
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)

    def test_switching_off_gates_its_api_and_writes_but_keeps_reads_and_data(self) -> None:
        dependents = module_settings.dependents("service")
        _set({m: 0 for m in dependents})
        rows_before = frappe.db.count("Service Ticket")
        _set({"service": 0})
        self.assertFalse(availability.module("service").available)
        with self.assertRaises(frappe.DoesNotExistError):
            module_settings.gate_api("zatgo_core.api.v1.service.tickets.list")
        self.assertFalse(module_settings.doc_has_permission(frappe.new_doc("Service Ticket"), "create"))
        self.assertTrue(module_settings.doc_has_permission(frappe.new_doc("Service Ticket"), "read"))
        self.assertTrue(module_settings.doc_has_permission(frappe.new_doc("Sales Invoice"), "create"),
                        "an ERPNext DocType is never gated by a module")
        self.assertEqual(frappe.db.count("Service Ticket"), rows_before, "switching off deletes nothing")
        _set({"service": 1})
        module_settings.gate_api("zatgo_core.api.v1.service.tickets.list")  # answers again
        self.assertTrue(module_settings.doc_has_permission(frappe.new_doc("Service Ticket"), "create"))

    def test_switching_off_a_module_switches_off_its_apps(self) -> None:
        if not app_state.switch_on("vansalex"):
            self.skipTest("VanSaleX is switched off on this site")
        _set({"vansalex": 0})
        self.assertFalse(app_state.is_on("vansalex"))
        self.assertIn("Module Settings", availability.app("vansalex").reason)
        _set({"vansalex": 1})
        self.assertTrue(app_state.is_on("vansalex"))

    def test_everything_on_changes_nothing(self) -> None:
        self.assertEqual(module_settings.disabled_modules(), frozenset())
        self.assertEqual(module_settings.blocked_api_prefixes(), ())
        self.assertEqual(module_settings.blocked_doctypes(), frozenset())

    def test_status_lists_every_module(self) -> None:
        status = {m["module"]: m for m in module_settings.status()}
        self.assertEqual(set(status), {m.id for m in registry.modules()})
        self.assertTrue(status["foundation"]["available"])
