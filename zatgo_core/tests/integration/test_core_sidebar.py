"""The "ZatGo" Desk sidebar has two sections -- Apps (the apps this site has switched on) and General Settings --
and follows the switches (services/core_sidebar.py)."""

from __future__ import annotations

from unittest import mock

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.api.v1 import app_hub
from zatgo_core.services import app_catalog, core_sidebar
from zatgo_core.setup.ensure_core_desk import ensure_core_desk

SETTINGS = "ZG System Settings"
FIELDS = ("enable_chat_ai", "enable_tracker", "enable_zatgo_space", "enable_saas_theme", "enable_language_switcher", "enable_vansalex_web")
APP_SETTINGS = ("VanSaleX Settings", "Chat AI Settings", "Tracker Settings", "Space Settings")


def _sidebar() -> list[dict]:
    doc = frappe.get_doc("Workspace Sidebar", core_sidebar.NAME)
    return [
        {"type": r.type, "label": r.label, "link_type": r.link_type, "link_to": r.link_to, "child": int(r.child or 0)}
        for r in doc.items
    ]


def _section(label: str) -> list[dict]:
    """The rows of one section, in order."""
    out, inside = [], False
    for row in _sidebar():
        if row["type"] == "Section Break":
            inside = row["label"] == label
        elif inside:
            out.append(row)
    return out


def _apps() -> dict[str, dict]:
    return {r["label"]: r for r in _section(core_sidebar.APPS_LABEL)}


def _general() -> list[dict]:
    return _section(core_sidebar.GENERAL_LABEL)


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

    def test_two_sections_apps_then_general_settings_and_every_row_nests_under_one(self) -> None:
        rows = _sidebar()
        sections = [r["label"] for r in rows if r["type"] == "Section Break"]
        self.assertEqual(sections, [core_sidebar.APPS_LABEL, core_sidebar.GENERAL_LABEL])
        self.assertEqual((core_sidebar.APPS_LABEL, core_sidebar.GENERAL_LABEL), ("Apps", "General Settings"))
        self.assertEqual(rows[0]["type"], "Section Break")
        # Nothing at top level besides the two captions: a link there would look like part of a section.
        self.assertTrue(all(r["child"] == 1 for r in rows if r["type"] == "Link"))

    def test_vansalex_is_one_entry_that_opens_its_workspace(self) -> None:
        self._switch()
        row = _apps()["ZatGo VanSaleX"]
        self.assertEqual((row["type"], row["child"], row["link_type"], row["link_to"]), ("Link", 1, "Workspace", "ZatGo VanSaleX"))
        # No sub-group and no "Overview" row any more: the app's page holds them.
        self.assertNotIn("Overview", {r["label"] for r in _sidebar()})

    def test_switched_off_apps_are_left_out(self) -> None:
        self._switch()
        self.assertFalse(set(_apps()) & {"ZatGo AI", "ZatGo Tracker", "ZatGo Space"})

    def test_switching_an_app_on_adds_it_and_off_removes_it(self) -> None:
        self._switch()
        for field, label in (("enable_tracker", "ZatGo Tracker"), ("enable_chat_ai", "ZatGo AI"), ("enable_zatgo_space", "ZatGo Space")):
            self._switch(**{field: 1})
            row = _apps().get(label)
            self.assertIsNotNone(row, f"{label} missing after switching it on")
            self.assertEqual(row["child"], 1)
            self.assertTrue(frappe.db.exists(row["link_type"], row["link_to"]), f"{label} -> {row['link_type']} {row['link_to']}")
            self._switch()
            self.assertNotIn(label, _apps(), f"{label} still listed after switching it off")

    def test_apps_switched_on_through_the_hub_open_their_workspace(self) -> None:
        """Switched on through the hub (what creates an app's Workspace), as on a real site."""
        self._switch()
        for key in ("tracker", "chat_ai", "zatgo_space"):
            app_hub.set_switch(key, 1)
            self.addCleanup(app_hub.set_switch, key, 0)
        apps = _apps()
        for label in ("ZatGo Tracker", "ZatGo AI", "ZatGo Space"):
            self.assertEqual((apps[label]["link_type"], apps[label]["link_to"]), ("Workspace", label), label)
            # The rail icon the module's own set-up just made stays hidden: apps open from ZatGo > Apps.
            for hidden in frappe.get_all("Desktop Icon", filters={"link_to": label}, pluck="hidden"):
                self.assertEqual(int(hidden or 0), 1, f"{label}: rail icon should be hidden")
        # Their own settings are tabs of the app's page, not sidebar entries (an app *without* a Workspace
        # falls back to its settings form, which is why this is checked with real Workspaces).
        linked = {r["link_to"] for r in _sidebar()}
        for doctype in APP_SETTINGS:
            self.assertNotIn(doctype, linked, f"{doctype} should be a tab, not a sidebar entry")

    def test_flipping_the_switch_in_the_hub_updates_the_sidebar_at_once(self) -> None:
        """No explicit sync: ZG System Settings' own save (what the hub uses) refreshes it."""
        self._switch()
        self.assertTrue(app_hub.set_switch("tracker", 1)["data"]["enabled"])
        self.assertIn("ZatGo Tracker", _apps())
        self.assertFalse(app_hub.set_switch("tracker", 0)["data"]["enabled"])
        self.assertNotIn("ZatGo Tracker", _apps())

    def test_switch_only_apps_are_general_settings_that_open_the_hub(self) -> None:
        """The theme, language switcher and VanSaleX web have no page of their own: listed while on, in General
        Settings, ahead of the hub itself (Frappe highlights the last item whose path matches)."""
        self._switch()
        names = {"ZatGo Desk Theme", "ZatGo Language Switcher", "ZatGo VanSaleX Web"}
        self.assertFalse({r["label"] for r in _general()} & names)
        for field, label in (
            ("enable_saas_theme", "ZatGo Desk Theme"),
            ("enable_language_switcher", "ZatGo Language Switcher"),
            ("enable_vansalex_web", "ZatGo VanSaleX Web"),
        ):
            self._switch(**{field: 1})
            general = _general()
            row = next((r for r in general if r["label"] == label), None)
            self.assertIsNotNone(row, label)
            self.assertEqual((row["child"], row["link_type"], row["link_to"]), (1, "Page", core_sidebar.HUB_PAGE))
            self.assertNotIn(label, _apps())
            hub_at = max(i for i, r in enumerate(general) if r["link_to"] == core_sidebar.HUB_PAGE)
            self.assertEqual(general[hub_at]["label"], core_sidebar.HUB_LABEL, "the hub must be the last entry that opens the hub")

    def test_general_settings_have_the_hub_and_the_platform_shortcuts(self) -> None:
        rows = _general()
        self.assertTrue(any(r["link_type"] == "Page" and r["link_to"] == core_sidebar.HUB_PAGE for r in rows))
        linked = {r["link_to"] for r in rows}
        for doctype in ("ZG System Settings", "ZG Company Settings", "ZG Security Settings", "ZG Audit Log"):
            self.assertIn(doctype, linked)

    def test_sync_is_idempotent(self) -> None:
        core_sidebar.sync_core_sidebar()
        self.assertFalse(core_sidebar.sync_core_sidebar())  # nothing drifted: nothing saved

    def test_a_flag_only_change_is_drift(self) -> None:
        """The fingerprint covers how a row renders, not only where it points."""
        frappe.db.set_value("Workspace Sidebar Item", {"parent": core_sidebar.NAME, "type": "Link"}, "show_arrow", 1)
        self.assertTrue(core_sidebar.sync_core_sidebar())
        self.assertFalse(core_sidebar.sync_core_sidebar())

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
            row = next(r for r in core_sidebar.app_links() if r["label"] == "Fake App")
        # Without a Workspace the entry opens its first settings DocType.
        self.assertEqual((row["type"], row["child"], row["link_type"], row["link_to"]), ("Link", 1, "DocType", "ToDo"))

    def test_a_new_sub_app_with_a_workspace_is_one_entry_to_it(self) -> None:
        fake = {
            "key": "fake_app", "label": "Fake App", "group": "bundled", "icon": "cloud", "switch_field": None,
            "workspaces": ("ZatGo",), "settings": (("ToDo", "My To Dos"),), "module_def": "Fake", "folder": "fake_app",
        }
        with mock.patch.object(app_catalog, "catalog", return_value=(*app_catalog.catalog(), fake)):
            rows = core_sidebar.app_links()
        fakes = [r for r in rows if r["label"] == "Fake App"]
        self.assertEqual(len(fakes), 1)
        self.assertEqual((fakes[0]["link_type"], fakes[0]["link_to"], fakes[0]["child"]), ("Workspace", "ZatGo", 1))

    def test_destination_must_exist(self) -> None:
        """A link to something missing would make Frappe hide or break the entry: it is dropped."""
        fake = {
            "key": "ghost", "label": "Ghost", "group": "bundled", "icon": "cloud", "switch_field": None,
            "workspaces": ("No Such Workspace",), "settings": (("No Such DocType", "x"),), "module_def": "Ghost",
            "folder": "ghost",
        }
        with mock.patch.object(app_catalog, "catalog", return_value=(*app_catalog.catalog(), fake)):
            self.assertNotIn("Ghost", {r["label"] for r in core_sidebar.app_links()})

    def test_enabled_industries_are_apps_too(self) -> None:
        from zatgo_core.industries import registry

        industry = next(i for i in registry.INDUSTRIES.values() if i.implemented)
        original = frappe.db.exists

        def exists(doctype, name=None, *args, **kwargs):
            if (doctype, name) == ("Workspace", industry.workspace):
                return True  # the industry's Workspace is made when it is switched on
            return original(doctype, name, *args, **kwargs)

        with mock.patch("zatgo_core.industries.gate.enabled_keys", return_value={industry.key}), mock.patch.object(
            frappe.db, "exists", exists
        ):
            rows = core_sidebar.app_links()
        row = next(r for r in rows if r["label"] == industry.workspace)
        self.assertEqual((row["link_type"], row["link_to"], row["child"]), ("Workspace", industry.workspace, 1))

    def test_name_matches_the_desktop_icon(self) -> None:
        """Frappe v16: an icon is shown only when its label equals the sidebar name."""
        self.assertEqual(frappe.db.get_value("Desktop Icon", core_sidebar.NAME, "link_to"), core_sidebar.NAME)
