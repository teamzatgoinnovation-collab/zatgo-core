"""The "ZatGo" Desk sidebar is General Settings only (the apps have their own sidebars) and follows the
switches (services/core_sidebar.py)."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.services import core_sidebar
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

    def test_one_section_general_settings_and_every_row_nests_under_it(self) -> None:
        rows = _sidebar()
        sections = [r["label"] for r in rows if r["type"] == "Section Break"]
        self.assertEqual(sections, [core_sidebar.GENERAL_LABEL])
        self.assertEqual(core_sidebar.GENERAL_LABEL, "General Settings")
        self.assertEqual(rows[0]["type"], "Section Break")
        # Nothing at top level besides the caption: a link there would look like part of the section.
        self.assertTrue(all(r["child"] == 1 for r in rows if r["type"] == "Link"))

    def test_apps_are_not_in_the_zatgo_sidebar(self) -> None:
        """Each app has its own sidebar (services/app_sidebar.py); the ZatGo one holds platform settings only."""
        self._switch()
        for label in ("ZatGo VanSaleX", "ZatGo AI", "ZatGo Tracker", "ZatGo Space"):
            self.assertNotIn(label, {r["label"] for r in _sidebar()})
        linked = {r["link_to"] for r in _sidebar()}
        for doctype in APP_SETTINGS:
            self.assertNotIn(doctype, linked, f"{doctype} belongs to its app's sidebar")

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
        self.assertTrue(_general())
