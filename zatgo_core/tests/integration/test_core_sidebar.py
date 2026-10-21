"""The "ZatGo" Desk sidebar lists the apps this site has switched on, and follows the switches
(services/core_sidebar.py)."""

from __future__ import annotations

from unittest import mock

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.api.v1 import app_hub
from zatgo_core.services import app_catalog, core_sidebar
from zatgo_core.setup.ensure_core_desk import ensure_core_desk

SETTINGS = "ZG System Settings"
FIELDS = ("enable_chat_ai", "enable_tracker", "enable_zatgo_space", "enable_saas_theme", "enable_language_switcher", "enable_vansalex_web")


def _sidebar() -> list[dict]:
    doc = frappe.get_doc("Workspace Sidebar", core_sidebar.NAME)
    return [
        {"type": r.type, "label": r.label, "link_type": r.link_type, "link_to": r.link_to, "child": int(r.child or 0)}
        for r in doc.items
    ]


def _apps() -> list[dict]:
    """Rows of the 'Apps' group."""
    out, in_apps = [], False
    for row in _sidebar():
        if row["type"] == "Section Break":
            in_apps = row["label"] == core_sidebar.APPS_LABEL
        elif in_apps:
            out.append(row)
    return out


def _settings() -> list[dict]:
    out, in_settings = [], False
    for row in _sidebar():
        if row["type"] == "Section Break":
            in_settings = row["label"] == core_sidebar.SETTINGS_LABEL
        elif in_settings:
            out.append(row)
    return out


class TestCoreSidebar(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self._before = {f: frappe.db.get_single_value(SETTINGS, f) for f in FIELDS}
        ensure_core_desk()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for f, v in self._before.items():
            frappe.db.set_single_value(SETTINGS, f, v or 0)
        frappe.clear_document_cache(SETTINGS, SETTINGS)
        core_sidebar.sync_core_sidebar()
        frappe.db.commit()

    def _switch(self, **values: int) -> None:
        for f in FIELDS:
            frappe.db.set_single_value(SETTINGS, f, values.get(f, 0))
        frappe.clear_document_cache(SETTINGS, SETTINGS)
        core_sidebar.sync_core_sidebar()

    def test_has_both_groups_and_nests_the_links(self) -> None:
        rows = _sidebar()
        sections = [r["label"] for r in rows if r["type"] == "Section Break"]
        self.assertEqual(sections, [core_sidebar.APPS_LABEL, core_sidebar.SETTINGS_LABEL])
        self.assertTrue(all(r["child"] == 1 for r in rows if r["type"] == "Link"))

    def test_vansalex_is_always_listed(self) -> None:
        self._switch()
        labels = {r["label"]: r for r in _apps()}
        self.assertIn("ZatGo VanSaleX", labels)
        self.assertIn(labels["ZatGo VanSaleX"]["link_type"], ("Workspace", "DocType"))

    def test_switched_off_apps_are_left_out(self) -> None:
        self._switch()
        labels = {r["label"] for r in _apps()}
        self.assertFalse(labels & {"ZatGo AI", "ZatGo Tracker", "ZatGo Space"})

    def test_switching_an_app_on_adds_it_and_off_removes_it(self) -> None:
        self._switch()
        for field, label in (("enable_tracker", "ZatGo Tracker"), ("enable_chat_ai", "ZatGo AI"), ("enable_zatgo_space", "ZatGo Space")):
            self._switch(**{field: 1})
            row = next((r for r in _apps() if r["label"] == label), None)
            self.assertIsNotNone(row, f"{label} missing after switching it on")
            self.assertTrue(frappe.db.exists(row["link_type"], row["link_to"]), f"{label} -> {row['link_type']} {row['link_to']}")
            self._switch()
            self.assertFalse([r for r in _apps() if r["label"] == label], f"{label} still listed after switching it off")

    def test_flipping_the_switch_in_the_hub_updates_the_sidebar_at_once(self) -> None:
        """No explicit sync: ZG System Settings' own save (what the hub uses) refreshes it."""
        self._switch()
        self.assertTrue(app_hub.set_switch("tracker", 1)["data"]["enabled"])
        self.assertIn("ZatGo Tracker", {r["label"] for r in _apps()})
        self.assertFalse(app_hub.set_switch("tracker", 0)["data"]["enabled"])
        self.assertNotIn("ZatGo Tracker", {r["label"] for r in _apps()})

    def test_switch_only_apps_are_listed_while_on_and_open_the_hub(self) -> None:
        """The theme, language switcher and VanSaleX web are apps too: no page of their own."""
        self._switch()
        self.assertFalse({r["label"] for r in _apps()} & {"ZatGo Desk Theme", "ZatGo Language Switcher", "ZatGo VanSaleX Web"})
        for field, label in (
            ("enable_saas_theme", "ZatGo Desk Theme"),
            ("enable_language_switcher", "ZatGo Language Switcher"),
            ("enable_vansalex_web", "ZatGo VanSaleX Web"),
        ):
            self._switch(**{field: 1})
            row = next((r for r in _apps() if r["label"] == label), None)
            self.assertIsNotNone(row, label)
            self.assertEqual((row["link_type"], row["link_to"]), ("Page", core_sidebar.HUB_PAGE))

    def test_an_app_without_a_workspace_opens_its_settings(self) -> None:
        self._switch(enable_zatgo_space=1)
        row = next(r for r in _apps() if r["label"] == "ZatGo Space")
        self.assertEqual((row["link_type"], row["link_to"]), ("DocType", "Space Settings"))

    def test_settings_group_has_the_hub_first_and_the_old_shortcuts(self) -> None:
        rows = _settings()
        self.assertEqual((rows[0]["link_type"], rows[0]["link_to"]), ("Page", core_sidebar.HUB_PAGE))
        linked = {r["link_to"] for r in rows}
        for doctype in ("ZG System Settings", "VanSaleX Settings", "ZG Security Settings", "ZG Audit Log"):
            self.assertIn(doctype, linked)

    def test_sync_is_idempotent(self) -> None:
        core_sidebar.sync_core_sidebar()
        self.assertFalse(core_sidebar.sync_core_sidebar())  # nothing drifted: nothing saved

    def test_a_stale_sidebar_is_repaired(self) -> None:
        """The sidebar used to be frozen at first creation: a leftover old list must be replaced."""
        sb = frappe.get_doc("Workspace Sidebar", core_sidebar.NAME)
        sb.set("items", [])
        sb.append("items", {"type": "Link", "label": "Old", "link_type": "DocType", "link_to": "ZG System Settings"})
        sb.flags.ignore_links = True
        sb.save(ignore_permissions=True)
        self.assertTrue(core_sidebar.sync_core_sidebar())
        self.assertNotIn("Old", {r["label"] for r in _sidebar()})
        self.assertTrue(_apps())

    def test_a_new_sub_app_appears_with_nothing_else_edited(self) -> None:
        fake = {
            "key": "fake_app", "label": "Fake App", "group": "bundled", "icon": "cloud", "switch_field": None,
            "workspaces": (), "settings": (("ToDo", "ToDo"),), "module_def": "Fake", "folder": "fake_app",
        }
        with mock.patch.object(app_catalog, "catalog", return_value=(*app_catalog.catalog(), fake)):
            self.assertIn("Fake App", {r["label"] for r in core_sidebar.app_links()})

    def test_destination_must_exist(self) -> None:
        """A link to something missing would make Frappe hide or break the entry: it is dropped."""
        fake = {
            "key": "ghost", "label": "Ghost", "group": "bundled", "icon": "cloud", "switch_field": None,
            "workspaces": ("No Such Workspace",), "settings": (("No Such DocType", "x"),), "module_def": "Ghost",
            "folder": "ghost",
        }
        with mock.patch.object(app_catalog, "catalog", return_value=(*app_catalog.catalog(), fake)):
            self.assertNotIn("Ghost", {r["label"] for r in core_sidebar.app_links()})

    def test_name_matches_the_desktop_icon(self) -> None:
        """Frappe v16: an icon is shown only when its label equals the sidebar name."""
        self.assertEqual(frappe.db.get_value("Desktop Icon", core_sidebar.NAME, "link_to"), core_sidebar.NAME)
