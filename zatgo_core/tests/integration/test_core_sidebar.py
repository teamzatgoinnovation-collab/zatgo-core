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


def _entries() -> list[dict]:
    """What comes before the general Settings group, one dict per app: a group (its children) or a link."""
    out: list[dict] = []
    for row in _sidebar():
        if row["type"] == "Section Break":
            if row["label"] == core_sidebar.SETTINGS_LABEL:
                break
            out.append({**row, "children": []})
        elif row["child"] and out and out[-1]["type"] == "Section Break":
            out[-1]["children"].append(row)
        else:
            out.append({**row, "children": []})
    return out


def _apps() -> dict[str, dict]:
    return {e["label"]: e for e in _entries()}


def _settings() -> list[dict]:
    out, in_settings = [], False
    for row in _sidebar():
        if row["type"] == "Section Break":
            in_settings = row["label"] == core_sidebar.SETTINGS_LABEL
        elif in_settings:
            out.append(row)
    return out


def _targets(entry: dict) -> list[tuple[str, str]]:
    rows = entry["children"] or [entry]
    return [(r["link_type"], r["link_to"]) for r in rows]


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

    def test_apps_come_first_and_settings_is_the_last_group(self) -> None:
        sections = [r["label"] for r in _sidebar() if r["type"] == "Section Break"]
        self.assertEqual(sections[-1], core_sidebar.SETTINGS_LABEL)
        self.assertNotIn("Apps", sections)  # one group per app, no catch-all caption
        rows = _sidebar()
        last_group = max(i for i, r in enumerate(rows) if r["type"] == "Section Break")
        self.assertTrue(all(r["child"] == 1 for r in rows[last_group + 1 :]))  # the settings links nest under it

    def test_single_links_come_before_every_group(self) -> None:
        """A link right after a group would look like one of its items."""
        self._switch(enable_saas_theme=1, enable_zatgo_space=1)
        rows = _sidebar()
        first_group = next(i for i, r in enumerate(rows) if r["type"] == "Section Break")
        self.assertTrue(first_group >= 2, "the single links should be above the first group")
        self.assertTrue(all(r["type"] == "Link" and r["child"] == 0 for r in rows[:first_group]))
        apps_part = [r for r in rows if r["type"] == "Section Break"][:-1]  # every group but Settings
        self.assertTrue(apps_part)
        after_groups = rows[first_group:]
        self.assertTrue(all(r["type"] == "Section Break" or r["child"] == 1 for r in after_groups))

    def test_vansalex_is_a_group_with_its_workspace_and_its_own_settings(self) -> None:
        self._switch()
        group = _apps()["ZatGo VanSaleX"]
        self.assertEqual(group["type"], "Section Break")
        self.assertTrue(all(c["child"] == 1 for c in group["children"]))
        self.assertEqual(
            [(c["label"], c["link_type"], c["link_to"]) for c in group["children"]],
            [(core_sidebar.OVERVIEW_LABEL, "Workspace", "ZatGo VanSaleX"), ("VanSaleX Settings", "DocType", "VanSaleX Settings")],
        )

    def test_an_apps_own_settings_are_not_in_the_general_settings_group(self) -> None:
        self._switch(enable_chat_ai=1, enable_tracker=1, enable_zatgo_space=1)
        general = {r["link_to"] for r in _settings()}
        for doctype in ("VanSaleX Settings", "Chat AI Settings", "Tracker Settings", "Space Settings"):
            self.assertNotIn(doctype, general)
        in_groups = {t for e in _entries() for _kind, t in _targets(e)}
        for doctype in ("VanSaleX Settings", "Chat AI Settings", "Tracker Settings", "Space Settings"):
            self.assertIn(doctype, in_groups, f"{doctype} should be in its app's entry")

    def test_switched_off_apps_are_left_out(self) -> None:
        self._switch()
        self.assertFalse(set(_apps()) & {"ZatGo AI", "ZatGo Tracker", "ZatGo Space"})

    def test_switching_an_app_on_adds_it_and_off_removes_it(self) -> None:
        self._switch()
        for field, label in (("enable_tracker", "ZatGo Tracker"), ("enable_chat_ai", "ZatGo AI"), ("enable_zatgo_space", "ZatGo Space")):
            self._switch(**{field: 1})
            entry = _apps().get(label)
            self.assertIsNotNone(entry, f"{label} missing after switching it on")
            for link_type, link_to in _targets(entry):
                self.assertTrue(frappe.db.exists(link_type, link_to), f"{label} -> {link_type} {link_to}")
            self._switch()
            self.assertNotIn(label, _apps(), f"{label} still listed after switching it off")

    def test_tracker_and_ai_are_groups_and_space_is_a_single_link(self) -> None:
        """Switched on through the hub (what creates an app's Workspace), as on a real site."""
        self._switch()
        for key in ("tracker", "chat_ai", "zatgo_space"):
            app_hub.set_switch(key, 1)
            self.addCleanup(app_hub.set_switch, key, 0)
        apps = _apps()
        for label, settings in (("ZatGo Tracker", "Tracker Settings"), ("ZatGo AI", "Chat AI Settings")):
            self.assertEqual(apps[label]["type"], "Section Break", label)
            self.assertEqual(
                [(c["label"], c["link_type"]) for c in apps[label]["children"]],
                [(core_sidebar.OVERVIEW_LABEL, "Workspace"), (settings, "DocType")],
            )
        space = apps["ZatGo Space"]
        self.assertEqual((space["type"], space["child"], space["link_type"], space["link_to"]), ("Link", 0, "DocType", "Space Settings"))

    def test_flipping_the_switch_in_the_hub_updates_the_sidebar_at_once(self) -> None:
        """No explicit sync: ZG System Settings' own save (what the hub uses) refreshes it."""
        self._switch()
        self.assertTrue(app_hub.set_switch("tracker", 1)["data"]["enabled"])
        self.assertIn("ZatGo Tracker", _apps())
        self.assertFalse(app_hub.set_switch("tracker", 0)["data"]["enabled"])
        self.assertNotIn("ZatGo Tracker", _apps())

    def test_switch_only_apps_are_listed_while_on_and_open_the_hub(self) -> None:
        """The theme, language switcher and VanSaleX web are apps too: no page of their own."""
        self._switch()
        self.assertFalse(set(_apps()) & {"ZatGo Desk Theme", "ZatGo Language Switcher", "ZatGo VanSaleX Web"})
        for field, label in (
            ("enable_saas_theme", "ZatGo Desk Theme"),
            ("enable_language_switcher", "ZatGo Language Switcher"),
            ("enable_vansalex_web", "ZatGo VanSaleX Web"),
        ):
            self._switch(**{field: 1})
            row = _apps().get(label)
            self.assertIsNotNone(row, label)
            self.assertEqual((row["type"], row["child"], row["link_type"], row["link_to"]), ("Link", 0, "Page", core_sidebar.HUB_PAGE))

    def test_settings_group_has_the_hub_first_and_the_general_shortcuts(self) -> None:
        rows = _settings()
        self.assertEqual((rows[0]["link_type"], rows[0]["link_to"]), ("Page", core_sidebar.HUB_PAGE))
        linked = {r["link_to"] for r in rows}
        for doctype in ("ZG System Settings", "ZG Company Settings", "ZG Security Settings", "ZG Audit Log"):
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
            row = next(r for r in core_sidebar.app_rows() if r["label"] == "Fake App")
        self.assertEqual((row["type"], row["child"], row["link_type"], row["link_to"]), ("Link", 0, "DocType", "ToDo"))

    def test_a_new_sub_app_with_a_workspace_and_settings_gets_a_group(self) -> None:
        fake = {
            "key": "fake_app", "label": "Fake App", "group": "bundled", "icon": "cloud", "switch_field": None,
            "workspaces": ("ZatGo",), "settings": (("ToDo", "My To Dos"),), "module_def": "Fake", "folder": "fake_app",
        }
        with mock.patch.object(app_catalog, "catalog", return_value=(*app_catalog.catalog(), fake)):
            rows = core_sidebar.app_rows()
        i = next(i for i, r in enumerate(rows) if r["label"] == "Fake App")
        self.assertEqual(rows[i]["type"], "Section Break")
        self.assertEqual([(r["label"], r["link_to"]) for r in rows[i + 1 : i + 3]], [("Overview", "ZatGo"), ("My To Dos", "ToDo")])
        self.assertTrue(all(r["child"] == 1 for r in rows[i + 1 : i + 3]))

    def test_destination_must_exist(self) -> None:
        """A link to something missing would make Frappe hide or break the entry: it is dropped."""
        fake = {
            "key": "ghost", "label": "Ghost", "group": "bundled", "icon": "cloud", "switch_field": None,
            "workspaces": ("No Such Workspace",), "settings": (("No Such DocType", "x"),), "module_def": "Ghost",
            "folder": "ghost",
        }
        with mock.patch.object(app_catalog, "catalog", return_value=(*app_catalog.catalog(), fake)):
            self.assertNotIn("Ghost", {r["label"] for r in core_sidebar.app_rows()})

    def test_name_matches_the_desktop_icon(self) -> None:
        """Frappe v16: an icon is shown only when its label equals the sidebar name."""
        self.assertEqual(frappe.db.get_value("Desktop Icon", core_sidebar.NAME, "link_to"), core_sidebar.NAME)
