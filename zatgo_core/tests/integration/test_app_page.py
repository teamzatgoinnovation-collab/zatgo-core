"""The sidebar of each ZatGo app (services/app_sidebar.py, services/app_page.py, events/boot.py), the tabs of the
settings forms it lists, the old URLs and the rail icons.

Runs against a real site; users are throwaway and removed afterwards."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.events import boot
from zatgo_core.services import app_catalog, app_desk, app_page, app_sidebar, core_sidebar

# Settings DocTypes of the apps, and the tabs their forms must have (fieldnames).
APP_FORMS = {
    "VanSaleX Settings": ["payments_tab", "sales_warehouse_tab", "access_tab"],
    "Chat AI Settings": ["provider_tab", "conversation_tab", "safety_tab", "features_tab", "voice_files_tab", "costs_tab"],
    "Tracker Settings": ["settings_tab"],
    "Space Settings": ["settings_tab"],
    "ZG System Settings": ["general_tab", "erp_tab", "apps_tab", "industries_tab"],
    "ZG Theme Settings": ["brand_tab", "appearance_tab"],
    "ZG Language Settings": ["general_tab"],
    "ZG MyBis Settings": ["general_tab"],
    "ZG POS Settings": ["general_tab", "payments_tab", "receipt_tab", "offline_tab"],
}


def _user(*roles: str) -> str:
    email = f"apppage.{random_string(8).lower()}@zatgo.test"
    frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": "AppPage",
            "send_welcome_email": 0,
            "roles": [{"role": r} for r in roles if frappe.db.exists("Role", r)],
        }
    ).insert(ignore_permissions=True)
    return email


class TestAppPage(IntegrationTestCase):
    def setUp(self) -> None:
        frappe.set_user("Administrator")
        self._users: list[str] = []

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for email in self._users:
            frappe.delete_doc("User", email, force=True, ignore_permissions=True)

    def _make(self, *roles: str) -> str:
        email = _user(*roles)
        self._users.append(email)
        return email

    # -- the sidebars ------------------------------------------------------------------------------------

    def _items(self, label: str = "ZatGo VanSaleX") -> list:
        app = next(a for a in app_page.apps() if a["label"] == label)
        return frappe.get_doc("Workspace Sidebar", app_sidebar.sidebar_name(app)).items

    def test_vansalex_sidebar_is_overview_then_settings_then_the_workspace_groups(self) -> None:
        app_sidebar.sync_app_sidebars()
        items = self._items()
        first = items[0]
        self.assertEqual((first.label, first.link_type, first.link_to, int(first.child or 0)), ("Overview", "Workspace", "ZatGo VanSaleX", 0))
        settings = [i for i in items if i.link_to == "VanSaleX Settings"]
        self.assertEqual(
            [(i.label, i.navigate_to_tab) for i in settings],
            [("Payments", "payments_tab"), ("Sales & Warehouse", "sales_warehouse_tab"), ("Modules & Features", "access_tab")],
        )
        self.assertTrue(all(int(i.child or 0) == 1 for i in items[1:] if i.type == "Link"))
        self.assertEqual(items[1].type, "Section Break")
        self.assertNotEqual(items[-1].type, "Section Break", "a caption with nothing under it")

    def test_every_item_points_at_something_that_exists_and_each_group_has_links(self) -> None:
        app_sidebar.sync_app_sidebars()
        items = self._items()
        for i in items:
            if i.type == "Link":
                self.assertTrue(frappe.db.exists(i.link_type, i.link_to), f"{i.label}: {i.link_type} {i.link_to}")
        for a, b in zip(items, items[1:]):
            self.assertFalse(a.type == "Section Break" and b.type == "Section Break", a.label)

    def test_sync_is_idempotent_and_repairs_drift(self) -> None:
        app_sidebar.sync_app_sidebars()
        self.assertFalse(app_sidebar.sync_app_sidebars())
        name = app_sidebar.sidebar_name(app_page.find("zatgo-vansalex"))
        frappe.db.set_value("Workspace Sidebar Item", {"parent": name, "type": "Link", "link_to": "VanSaleX Settings"}, "navigate_to_tab", "access_tab")
        self.assertTrue(app_sidebar.sync_app_sidebars())
        self.assertFalse(app_sidebar.sync_app_sidebars())

    def test_a_switched_off_app_has_no_items_and_comes_back_on(self) -> None:
        tracker = app_page.find("zatgo-tracker")
        if not frappe.db.exists("Workspace Sidebar", app_sidebar.sidebar_name(tracker)) or app_page.is_enabled(tracker):
            self.skipTest("Tracker is on or was never set up on this site")
        app_sidebar.sync_app_sidebars()
        self.assertFalse(self._items("ZatGo Tracker"))

    def test_no_settings_form_is_listed_by_two_apps(self) -> None:
        owners: dict[str, list[str]] = {}
        for app in app_page.apps():
            for doctype, _label in app["settings"]:
                owners.setdefault(doctype, []).append(app["key"])
        self.assertEqual({d: o for d, o in owners.items() if len(o) > 1}, {})

    # -- routes ------------------------------------------------------------------------------------------

    def test_old_urls_open_the_apps_workspace(self) -> None:
        old = app_page.old_url_redirects()
        self.assertEqual(old["zg-app/zatgo-vansalex"], "zatgo-vansalex")
        self.assertEqual(old["vansalex"], "zatgo-vansalex")  # the workspace's name before it was "ZatGo ..."
        bootinfo = frappe._dict()
        boot.boot_session(bootinfo)
        self.assertEqual(bootinfo.zatgo_core["app_routes"]["zg-app/zatgo-vansalex"], "zatgo-vansalex")

    def test_the_folder_lists_only_apps_that_are_on_and_open_to_the_user(self) -> None:
        def folder(sidebars: dict, on: set[str]) -> dict:
            info = frappe._dict(
                workspace_sidebar_item=sidebars,
                desktop_icons=[frappe._dict(label="ZatGo", icon_type="Folder")],
            )
            with patch.object(app_page, "is_enabled", side_effect=lambda app: app["key"] in on):
                boot._zatgo_folder_children(info)
            return {i["label"]: i["link"] for i in info.desktop_icons if i.get("parent_icon") == "ZatGo"}

        def link(name: str) -> dict:
            return {"items": [{"type": "Link", "link_type": "Workspace", "link_to": name}]}

        sidebars = {
            "zatgo vansalex": link("ZatGo VanSaleX"),
            "zatgo desk theme": link("ZatGo Desk Theme"),
            "zatgo tracker": link("ZatGo Tracker"),
            "zatgo": {"items": [{"type": "Link", "link_type": "Page", "link_to": "zg-app-hub"}]},
        }
        self.assertEqual(
            folder(sidebars, {"vansalex", "saas_theme"}),
            {
                "ZatGo VanSaleX": "/desk/zatgo-vansalex",
                "ZatGo Desk Theme": "/desk/zatgo-desk-theme",
                "General Settings": "/desk/zg-app-hub",
            },
        )
        # Tracker has a sidebar but is off: not listed. An app that is on with no sidebar for this user: not listed.
        self.assertEqual(folder({"zatgo vansalex": sidebars["zatgo vansalex"]}, {"vansalex", "chat_ai"}), {"ZatGo VanSaleX": "/desk/zatgo-vansalex"})
        self.assertEqual(folder({}, set()), {})

    def test_every_switchable_app_gets_a_sidebar_with_its_settings_once_on(self) -> None:
        """Desk theme, language switcher, MyBis and VanSaleX web are apps like the rest: Overview + their settings."""
        wanted = {
            "ZatGo Desk Theme": "ZG Theme Settings",
            "ZatGo Language Switcher": "ZG Language Settings",
            "ZatGo MyBis": "ZG MyBis Settings",
            "ZatGo VanSaleX Web": None,
        }
        for label, settings in wanted.items():
            app = next(a for a in app_page.apps() if a["label"] == label)
            items = app_sidebar.desired_items(app)
            self.assertEqual(items[0]["label"], "Overview", label)
            self.assertEqual(items[0]["link_to"], label, label)
            if settings:
                self.assertIn(settings, {i.get("link_to") for i in items}, label)

    # -- settings forms ----------------------------------------------------------------------------------

    def test_settings_forms_are_tabbed_from_their_first_field(self) -> None:
        """No implicit "Details" tab: the first field of each is a Tab Break, and the tabs are the planned ones."""
        for doctype, tabs in APP_FORMS.items():
            meta = frappe.get_meta(doctype)
            self.assertEqual(meta.fields[0].fieldtype, "Tab Break", doctype)
            self.assertEqual([t["key"] for t in app_page.tab_breaks(doctype)], tabs, doctype)

    def test_every_settings_field_sits_under_a_tab(self) -> None:
        for doctype in APP_FORMS:
            seen_tab = False
            for df in frappe.get_meta(doctype).fields:
                seen_tab = seen_tab or df.fieldtype == "Tab Break"
                self.assertTrue(seen_tab, f"{doctype}.{df.fieldname} is above the first tab")

    # -- rail icons --------------------------------------------------------------------------------------

    def test_app_rail_icons_are_hidden_but_the_zatgo_icon_is_not(self) -> None:
        app_desk.sync_rail_icons()
        targets = app_desk.rail_icon_targets()
        icons = frappe.get_all("Desktop Icon", filters={"link_to": ["in", targets]}, fields=["name", "hidden"])
        for icon in icons:
            self.assertEqual(int(icon.hidden or 0), 1, f"{icon.name} should be hidden")
        self.assertEqual(int(frappe.db.get_value("Desktop Icon", core_sidebar.NAME, "hidden") or 0), 0)
        self.assertNotIn(core_sidebar.NAME, targets)

    def test_the_apps_workspaces_stay_visible_for_the_sidebar_to_link_to(self) -> None:
        """Only the rail icon is hidden, never the Workspace the Apps entry opens (a switched-off app's is)."""
        app_desk.sync_app_desk()
        self.assertEqual(int(frappe.db.get_value("Workspace", "ZatGo VanSaleX", "is_hidden") or 0), 0)

    def test_the_catalog_still_loads_clean(self) -> None:
        self.assertEqual(app_catalog.load_errors(), [])
