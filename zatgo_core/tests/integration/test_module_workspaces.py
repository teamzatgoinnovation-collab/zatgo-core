"""Module workspaces (Phase 6): created once with links that exist, shown only for enabled modules shown in navigation,
and hiding never switches a module's functions off."""

from __future__ import annotations

import json

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.services import module_settings, module_workspaces


def _set(field: str, states: dict[str, int]) -> None:
    doc = frappe.get_doc(module_settings.DOCTYPE)
    for row in doc.modules:
        if row.module in states:
            row.set(field, states[row.module])
    doc.save()


def _visible(name: str) -> bool:
    return not frappe.db.get_value("Workspace", name, "is_hidden") and not frappe.db.get_value("Desktop Icon", name, "hidden")


class TestModuleWorkspaces(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        module_workspaces.ensure()
        module_settings.sync_rows()
        rows = frappe.get_doc(module_settings.DOCTYPE).modules
        self.saved = {r.module: (r.enabled, r.show_in_navigation) for r in rows}

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        doc = frappe.get_doc(module_settings.DOCTYPE)
        for row in doc.modules:
            if row.module in self.saved:
                row.enabled, row.show_in_navigation = self.saved[row.module]
        doc.save()
        frappe.db.commit()

    def installed_specs(self):
        return [s for s in module_workspaces.specs() if module_settings.is_installed(s.module)]

    def test_a_workspace_per_installed_module_and_a_rerun_creates_none(self) -> None:
        for spec in self.installed_specs():
            self.assertTrue(frappe.db.exists("Workspace", spec.name), spec.name)
        self.assertEqual(module_workspaces.ensure(), [])

    def test_every_link_and_shortcut_points_at_something_that_exists(self) -> None:
        for spec in self.installed_specs():
            ws = frappe.get_doc("Workspace", spec.name)
            for link in ws.links:
                if link.type == "Link":
                    self.assertTrue(frappe.db.exists(link.link_type, link.link_to), f"{spec.name}: {link.link_to}")
            for sc in ws.shortcuts:
                self.assertTrue(frappe.db.exists("DocType", sc.link_to), f"{spec.name}: {sc.link_to}")
            for role in ws.roles:
                self.assertTrue(frappe.db.exists("Role", role.role), f"{spec.name}: role {role.role}")
            cards = {b["data"]["card_name"] for b in json.loads(ws.content) if b["type"] == "card"}
            self.assertEqual(cards, {l.label for l in ws.links if l.type == "Card Break"}, spec.name)

    def test_the_module_row_points_at_its_workspace(self) -> None:
        rows = {r.module: r for r in frappe.get_doc(module_settings.DOCTYPE).modules}
        self.assertEqual(rows["sales"].workspace, "ZatGo Sales")

    def test_hiding_from_navigation_keeps_the_module_working(self) -> None:
        _set("show_in_navigation", {"procurement": 0})
        self.assertFalse(_visible("ZatGo Purchase"))
        self.assertTrue(module_settings.is_enabled("procurement"))
        module_settings.gate_api("zatgo_core.api.v1.accounting.purchase_invoices.list")  # still answers
        self.assertFalse(frappe.db.get_value("Workspace Sidebar", "ZatGo Purchase") and
                         frappe.get_doc("Workspace Sidebar", "ZatGo Purchase").items, "a hidden module's sidebar is empty")
        _set("show_in_navigation", {"procurement": 1})
        self.assertTrue(_visible("ZatGo Purchase"))
        self.assertTrue(frappe.get_doc("Workspace Sidebar", "ZatGo Purchase").items)

    def test_switching_a_module_off_hides_its_workspace(self) -> None:
        _set("enabled", {m: 0 for m in module_settings.dependents("service")})
        _set("enabled", {"service": 0})
        self.assertFalse(_visible("ZatGo Service"))
        _set("enabled", {"service": 1})
        self.assertTrue(_visible("ZatGo Service"))

    def test_customer_a_sees_only_sales(self) -> None:
        """Customer A: Sales only in navigation. Stock and Accounting stay enabled (sales posts through them)."""
        others = {s.module: 0 for s in self.installed_specs() if s.module != "sales"}
        _set("show_in_navigation", others)
        visible = [s.name for s in self.installed_specs() if _visible(s.name)]
        self.assertEqual(visible, ["ZatGo Sales"])
        self.assertTrue(module_settings.is_enabled("accounting") and module_settings.is_enabled("inventory"))
