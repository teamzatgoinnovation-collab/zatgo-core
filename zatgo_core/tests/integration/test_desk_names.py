"""ZatGo AI / ZatGo Tracker / ZatGo VanSaleX: the Workspace, Workspace Sidebar and Desktop Icon carry the
"ZatGo ..." name, a site that still has the old names is migrated to them, and the old Desk URLs redirect."""

from __future__ import annotations

import json
import os
from unittest import mock

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.chat_ai import install as chat_install
from zatgo_core.services import app_catalog, core_sidebar, ui_apps
from zatgo_core.setup import ensure_core_desk as core_desk
from zatgo_core.tracker import install as tracker_install

RENAMES = {
    "chat_ai": ("ZatGo AI", ("AI Admin", "Chat AI")),
    "tracker": ("ZatGo Tracker", ("Tracker", "Task Management")),
}


def _make_workspace(name: str, module: str = "ZatGo Core") -> None:
    doc = frappe.get_doc(
        {"doctype": "Workspace", "label": name, "title": name, "public": 1, "module": module, "content": "[]"}
    )
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True)


def _drop(doctype: str, *names: str) -> None:
    for name in names:
        if frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)


class TestShippedRecords(IntegrationTestCase):
    """The JSON the app ships names everything "ZatGo ..." (nothing else to keep in step)."""

    def _json(self, *parts: str) -> dict:
        with open(frappe.get_app_path("zatgo_core", *parts), encoding="utf-8") as f:
            return json.load(f)

    def test_workspace_files_are_named_zatgo(self) -> None:
        for path, name in (
            (("chat_ai", "desk_records", "workspace", "ai_admin", "ai_admin.json"), "ZatGo AI"),
            (("tracker", "desk_records", "workspace", "tracker", "tracker.json"), "ZatGo Tracker"),
            (("tracker", "desk_records", "workspace_sidebar", "tracker.json"), "ZatGo Tracker"),
            (("zatgo_core", "workspace", "zatgo_vansalex", "zatgo_vansalex.json"), "ZatGo VanSaleX"),
        ):
            d = self._json(*path)
            self.assertEqual(d["name"], name, path)
            self.assertEqual(d["title"], name, path)

    def test_the_synced_vansalex_file_sits_where_frappe_looks(self) -> None:
        """Frappe syncs workspace/<scrub(name)>/<scrub(name)>.json: a mismatch would silently never import."""
        folder = frappe.scrub("ZatGo VanSaleX")
        self.assertTrue(os.path.isfile(frappe.get_app_path("zatgo_core", "zatgo_core", "workspace", folder, f"{folder}.json")))
        self.assertFalse(os.path.exists(frappe.get_app_path("zatgo_core", "zatgo_core", "workspace", "vansalex")))

    def test_manifests_list_the_new_name_first_and_keep_the_old_ones(self) -> None:
        by_key = {a["key"]: a for a in app_catalog.catalog()}
        for key, (new, legacy) in RENAMES.items():
            self.assertEqual(by_key[key]["workspaces"][0], new)
            for old in legacy:
                self.assertIn(old, by_key[key]["workspaces"])  # remove_desk_entries must still clean legacy names
        self.assertEqual(by_key["vansalex"]["workspaces"][:2], ("ZatGo VanSaleX", "VanSaleX"))


class TestRenameHelpers(IntegrationTestCase):
    """The migration paths, on throwaway records (the real workspaces are not touched)."""

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        tag = random_string(6)
        self.new, self.old1, self.old2 = f"ZG New {tag}", f"ZG Old {tag}", f"ZG Older {tag}"
        self.addCleanup(_drop, "Workspace", self.new, self.old1, self.old2)

    def test_tracker_helper_renames_a_legacy_record(self) -> None:
        _make_workspace(self.old1)
        self.assertTrue(tracker_install._adopt_desk_name("Workspace", self.new, (self.old1, self.old2)))
        self.assertTrue(frappe.db.exists("Workspace", self.new))
        self.assertFalse(frappe.db.exists("Workspace", self.old1))

    def test_tracker_helper_deletes_legacy_when_the_new_one_exists(self) -> None:
        _make_workspace(self.new)
        _make_workspace(self.old1)
        _make_workspace(self.old2)
        self.assertTrue(tracker_install._adopt_desk_name("Workspace", self.new, (self.old1, self.old2)))
        self.assertTrue(frappe.db.exists("Workspace", self.new))
        self.assertFalse(frappe.db.exists("Workspace", self.old1) or frappe.db.exists("Workspace", self.old2))

    def test_tracker_helper_is_idempotent_and_a_noop_without_legacy(self) -> None:
        _make_workspace(self.new)
        self.assertTrue(tracker_install._adopt_desk_name("Workspace", self.new, (self.old1,)))
        self.assertTrue(tracker_install._adopt_desk_name("Workspace", self.new, (self.old1,)))
        self.assertFalse(tracker_install._adopt_desk_name("Workspace", f"{self.new}-missing", (self.old1,)))

    def test_chat_ai_adopt_renames_and_repoints_sidebar_rows(self) -> None:
        _make_workspace(self.old1, module="Chat AI")
        side = frappe.get_doc(
            {
                "doctype": "Workspace Sidebar", "title": f"ZG Side {self.new}", "module": "Chat AI",
                "items": [{"type": "Link", "label": "Home", "link_type": "Workspace", "link_to": self.old1}],
            }
        )
        side.flags.ignore_links = True
        side.insert(ignore_permissions=True)
        self.addCleanup(_drop, "Workspace Sidebar", side.name)
        chat_install._adopt_workspace(self.new, (self.old1,))
        self.assertTrue(frappe.db.exists("Workspace", self.new))
        self.assertFalse(frappe.db.exists("Workspace", self.old1))
        self.assertEqual(frappe.db.get_value("Workspace Sidebar Item", {"parent": side.name}, "link_to"), self.new)

    def test_chat_ai_adopt_deletes_legacy_when_the_new_one_exists(self) -> None:
        _make_workspace(self.new, module="Chat AI")
        _make_workspace(self.old1, module="Chat AI")
        chat_install._adopt_workspace(self.new, (self.old1,))
        self.assertTrue(frappe.db.exists("Workspace", self.new))
        self.assertFalse(frappe.db.exists("Workspace", self.old1))

    def test_core_desk_retires_the_legacy_vansalex_style_workspace(self) -> None:
        _make_workspace(self.new)
        _make_workspace(self.old1)
        with mock.patch.dict(core_desk.LEGACY_WORKSPACES, {self.new: (self.old1,)}, clear=False):
            core_desk._retire_legacy_workspaces()
        self.assertTrue(frappe.db.exists("Workspace", self.new))
        self.assertFalse(frappe.db.exists("Workspace", self.old1))

    def test_core_desk_leaves_the_legacy_one_while_the_new_is_missing(self) -> None:
        _make_workspace(self.old1)
        with mock.patch.dict(core_desk.LEGACY_WORKSPACES, {self.new: (self.old1,)}, clear=False):
            core_desk._retire_legacy_workspaces()
        self.assertTrue(frappe.db.exists("Workspace", self.old1))  # never delete the only one


class TestLegacyRailEntry(IntegrationTestCase):
    """A site made before the rename has a rail icon + sidebar named after the old workspace (and migrate's
    orphan purge may already have deleted that workspace): they become the new name, links following."""

    def setUp(self) -> None:
        frappe.set_user("Administrator")
        tag = random_string(6)
        self.new, self.old = f"ZG New {tag}", f"ZG Old {tag}"
        self.addCleanup(_drop, "Desktop Icon", self.old, self.new)
        self.addCleanup(_drop, "Workspace Sidebar", self.old, self.new)
        self.addCleanup(_drop, "Workspace", self.old, self.new)

    def _sidebar(self, name: str, home: str) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Workspace Sidebar", "title": name, "module": "ZatGo Core", "header_icon": "sell",
                "items": [
                    {"type": "Link", "label": "Home", "link_type": "Workspace", "link_to": home},
                    {"type": "Link", "label": "To Dos", "link_type": "DocType", "link_to": "ToDo"},
                ],
            }
        )
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)

    def _icon(self, name: str, sidebar: str) -> None:
        doc = frappe.get_doc(
            {
                "doctype": "Desktop Icon", "label": name, "icon_type": "Link", "link_type": "Workspace Sidebar",
                "link_to": sidebar, "standard": 0, "hidden": 0,
            }
        )
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)

    def _retire(self) -> None:
        with mock.patch.dict(core_desk.LEGACY_WORKSPACES, {self.new: (self.old,)}, clear=False):
            core_desk._retire_legacy_workspaces()

    def test_the_legacy_sidebar_and_icon_are_renamed_and_repointed(self) -> None:
        _make_workspace(self.new)  # the old Workspace is already gone, as after migrate's orphan purge
        self._sidebar(self.old, home=self.old)
        self._icon(self.old, self.old)
        self._retire()
        self.assertFalse(frappe.db.exists("Workspace Sidebar", self.old) or frappe.db.exists("Desktop Icon", self.old))
        self.assertEqual(frappe.db.get_value("Workspace Sidebar", self.new, "title"), self.new)
        home = frappe.db.get_value("Workspace Sidebar Item", {"parent": self.new, "label": "Home"}, "link_to")
        self.assertEqual(home, self.new, "the sidebar's Home link must follow the workspace rename")
        icon = frappe.db.get_value("Desktop Icon", self.new, ["label", "link_type", "link_to"], as_dict=True)
        self.assertEqual((icon.label, icon.link_type, icon.link_to), (self.new, "Workspace Sidebar", self.new))

    def test_an_existing_new_entry_wins_and_the_legacy_one_is_deleted(self) -> None:
        _make_workspace(self.new)
        self._sidebar(self.new, home=self.new)
        self._icon(self.new, self.new)
        self._sidebar(self.old, home=self.old)
        self._icon(self.old, self.old)
        self._retire()
        self.assertFalse(frappe.db.exists("Workspace Sidebar", self.old) or frappe.db.exists("Desktop Icon", self.old))
        self.assertTrue(frappe.db.exists("Workspace Sidebar", self.new) and frappe.db.exists("Desktop Icon", self.new))

    def test_it_is_idempotent(self) -> None:
        _make_workspace(self.new)
        self._sidebar(self.old, home=self.old)
        self._icon(self.old, self.old)
        self._retire()
        self._retire()
        self.assertTrue(frappe.db.exists("Workspace Sidebar", self.new) and frappe.db.exists("Desktop Icon", self.new))

    def test_nothing_is_renamed_while_the_new_workspace_is_missing(self) -> None:
        self._sidebar(self.old, home=self.old)
        self._icon(self.old, self.old)
        self._retire()
        self.assertTrue(frappe.db.exists("Workspace Sidebar", self.old) and frappe.db.exists("Desktop Icon", self.old))
        self.assertFalse(frappe.db.exists("Workspace Sidebar", self.new))


class TestRealRecordsAfterSync(IntegrationTestCase):
    """What a migrated site looks like (the test site must have been migrated with this code)."""

    def test_vansalex_workspace_is_zatgo_named_and_the_old_one_is_gone(self) -> None:
        self.assertTrue(frappe.db.exists("Workspace", "ZatGo VanSaleX"))
        self.assertFalse(frappe.db.exists("Workspace", "VanSaleX"))

    def test_zatgo_sidebar_links_the_renamed_vansalex_workspace(self) -> None:
        frappe.set_user("Administrator")
        core_sidebar.sync_core_sidebar()
        row = frappe.db.get_value(
            "Workspace Sidebar Item", {"parent": "ZatGo", "link_type": "Workspace", "link_to": "ZatGo VanSaleX"}, ["label", "child"], as_dict=True
        )
        self.assertIsNotNone(row, "the ZatGo sidebar should link the renamed VanSaleX workspace")
        self.assertEqual((row.label, row.child), ("Overview", 1))  # inside the "ZatGo VanSaleX" group
        self.assertTrue(frappe.db.exists("Workspace Sidebar Item", {"parent": "ZatGo", "type": "Section Break", "label": "ZatGo VanSaleX"}))

    def test_enabled_apps_have_one_consistent_desk_name(self) -> None:
        from zatgo_core.services import bundled_apps

        for key, (new, legacy) in RENAMES.items():
            if not bundled_apps.is_on(key):
                continue
            self.assertTrue(frappe.db.exists("Workspace", new), f"{key}: Workspace {new}")
            self.assertTrue(frappe.db.exists("Workspace Sidebar", new), f"{key}: Workspace Sidebar {new}")
            icon = frappe.db.get_value("Desktop Icon", {"link_to": new}, ["name", "label"], as_dict=True)
            self.assertIsNotNone(icon, f"{key}: Desktop Icon -> {new}")
            self.assertEqual(icon.label, new)
            for old in legacy:
                for doctype in ("Workspace", "Workspace Sidebar"):
                    self.assertFalse(frappe.db.exists(doctype, old), f"{doctype} {old} should have been retired")


class TestOldUrlsRedirect(IntegrationTestCase):
    def _map(self) -> dict[str, str]:
        with open(frappe.get_app_path("zatgo_core", "public", "js", "zg_route_redirects.js"), encoding="utf-8") as f:
            text = f.read()
        body = text[text.index("Object.assign(frappe.re_route, {") :].split("});", 1)[0]
        return dict(
            (k.strip().strip('"'), v.strip().strip('",'))
            for k, v in (line.split(":", 1) for line in body.splitlines()[1:] if ":" in line)
        )

    def test_every_new_route_is_the_slug_of_a_zatgo_name(self) -> None:
        slugs = {frappe.scrub(n).replace("_", "-") for n, _ in RENAMES.values()} | {"zatgo-vansalex"}
        redirects = self._map()
        self.assertTrue(redirects)
        for old, new in redirects.items():
            self.assertIn(new, slugs, f"{old} -> {new}")

    def test_every_old_name_is_redirected(self) -> None:
        redirects = self._map()
        for _new, legacy in RENAMES.values():
            for old in legacy:
                self.assertIn(frappe.scrub(old).replace("_", "-"), redirects, old)
        self.assertIn("vansalex", redirects)

    def test_the_script_is_loaded_on_every_site(self) -> None:
        _css, js = ui_apps.desk_includes()
        self.assertTrue(any("zg_route_redirects.js" in u for u in js))
