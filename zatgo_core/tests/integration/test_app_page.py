"""ZatGo > Apps > <app>: the page behind each app entry (services/app_page.py, api/v1/app_page.py, events/boot.py),
the tabs of the settings forms and the rail icons.

Runs against a real site; users are throwaway and removed afterwards."""

from __future__ import annotations

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase
from frappe.utils import random_string

from zatgo_core.api.v1 import app_page as api
from zatgo_core.events import boot
from zatgo_core.services import app_catalog, app_desk, app_page, core_sidebar

# Settings DocTypes of the apps, and the tabs their forms must have (fieldnames).
APP_FORMS = {
    "VanSaleX Settings": ["payments_tab", "sales_warehouse_tab", "access_tab"],
    "Chat AI Settings": ["provider_tab", "conversation_tab", "safety_tab", "features_tab", "voice_files_tab", "costs_tab"],
    "Tracker Settings": ["settings_tab"],
    "Space Settings": ["settings_tab"],
    "ZG System Settings": ["general_tab", "erp_tab", "apps_tab", "industries_tab"],
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

    # -- routes ------------------------------------------------------------------------------------------

    def test_route_keys_are_label_slugs_and_resolve_back(self) -> None:
        vansalex = app_page.find("zatgo-vansalex")
        self.assertEqual((vansalex["key"], vansalex["route_key"]), ("vansalex", "zatgo-vansalex"))
        self.assertEqual(app_page.route_for(vansalex), "/desk/zg-app/zatgo-vansalex")
        self.assertEqual(app_page.find(" ZatGo-VanSaleX ")["key"], "vansalex")  # case / spaces do not matter
        self.assertEqual(app_page.find("chat-ai")["key"], "chat_ai")  # the bare key still resolves
        self.assertIsNone(app_page.find("no-such-app"))

    def test_route_keys_are_unique_and_never_a_sidebar_name(self) -> None:
        """For a two-part route Frappe opens the sidebar whose lower-cased name equals the second part: a key such as
        `tracker` would open the auto-generated "Tracker" module sidebar instead of ZatGo's."""
        keys = [a["route_key"] for a in app_page.apps()]
        self.assertEqual(len(keys), len(set(keys)), "two apps share a route key")
        self.assertEqual(len({a["key"] for a in app_page.apps()}), len(keys), "an app and an industry share a key")
        sidebars = {n.lower() for n in frappe.get_all("Workspace Sidebar", pluck="name")}
        for key in keys:
            self.assertNotIn(key, sidebars, f"/desk/zg-app/{key} would open that sidebar")
            self.assertIn("-", key)

    def test_every_workspace_of_an_app_routes_to_its_page(self) -> None:
        routes = app_page.workspace_routes()
        self.assertEqual(routes["ZatGo VanSaleX"], "/desk/zg-app/zatgo-vansalex")
        self.assertEqual(routes["ZatGo AI"], "/desk/zg-app/zatgo-ai")
        self.assertEqual(routes["ZatGo Tracker"], "/desk/zg-app/zatgo-tracker")
        self.assertEqual(routes["ZatGo Space"], "/desk/zg-app/zatgo-space")

    def test_old_desk_urls_are_redirected_to_the_page(self) -> None:
        old = app_page.old_url_redirects()
        self.assertEqual(old["zatgo-vansalex"], "zg-app/zatgo-vansalex")
        self.assertEqual(old["vansalex"], "zg-app/zatgo-vansalex")  # the workspace's name before it was "ZatGo ..."
        self.assertEqual(old["ai-admin"], "zg-app/zatgo-ai")
        self.assertEqual(old["task-management"], "zg-app/zatgo-tracker")

    def test_boot_points_the_app_entries_at_their_page_and_nothing_else(self) -> None:
        sidebar = frappe._dict(
            items=[
                {"label": "Apps", "type": "Section Break", "link_type": "DocType", "link_to": None},
                {"label": "ZatGo VanSaleX", "type": "Link", "link_type": "Workspace", "link_to": "ZatGo VanSaleX"},
                {"label": "Hub", "type": "Link", "link_type": "Page", "link_to": "zg-app-hub"},
                {"label": "Other", "type": "Link", "link_type": "Workspace", "link_to": "Home"},
            ]
        )
        bootinfo = frappe._dict(workspace_sidebar_item={core_sidebar.NAME.lower(): sidebar, "email": frappe._dict(items=[])})
        boot._route_sidebar_entries(bootinfo)
        routes = {i["label"]: i.get("route") for i in sidebar["items"]}
        self.assertEqual(routes, {"Apps": None, "ZatGo VanSaleX": "/desk/zg-app/zatgo-vansalex", "Hub": None, "Other": None})

    def test_boot_session_hands_the_page_the_maps_it_needs(self) -> None:
        bootinfo = frappe._dict()
        boot.boot_session(bootinfo)
        self.assertEqual(bootinfo.zatgo_core["app_settings"]["VanSaleX Settings"], "zatgo-vansalex")
        self.assertEqual(bootinfo.zatgo_core["app_routes"]["zatgo-vansalex"], "zg-app/zatgo-vansalex")

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

    def test_settings_routes_cover_every_apps_settings_form(self) -> None:
        routes = app_page.settings_routes()
        for doctype in ("VanSaleX Settings", "Chat AI Settings", "Tracker Settings", "Space Settings"):
            self.assertIn(doctype, routes)

    # -- the page's data ---------------------------------------------------------------------------------

    def test_a_system_manager_gets_overview_then_the_settings_tabs(self) -> None:
        data = app_page.build("zatgo-vansalex")
        self.assertEqual(data["app"]["route_key"], "zatgo-vansalex")
        tabs = data["tabs"]
        self.assertEqual(tabs[0], {"key": "overview", "label": "Overview", "kind": "overview"})
        self.assertEqual(
            [(t["label"], t["tab"]) for t in tabs[1:]],
            [("Payments", "payments_tab"), ("Sales & Warehouse", "sales_warehouse_tab"), ("Modules & Features", "access_tab")],
        )
        self.assertTrue(all(t["doctype"] == "VanSaleX Settings" for t in tabs[1:]))

    def test_the_overview_comes_from_the_apps_workspace(self) -> None:
        data = app_page.build("zatgo-vansalex")
        overview = data["overview"]
        self.assertEqual(overview["workspace"], "ZatGo VanSaleX")
        sections = {s["label"]: [link["name"] for link in s["links"]] for s in overview["sections"]}
        self.assertIn("Setup", sections)
        self.assertIn("VanSaleX Settings", sections["Setup"])
        self.assertTrue(overview["shortcuts"])
        for link in [link for s in overview["sections"] for link in s["links"]]:
            self.assertTrue(frappe.db.exists(link["type"], link["name"]), link)

    def test_unknown_and_switched_off_apps_are_refused_with_a_reason(self) -> None:
        with self.assertRaises(app_page.AppPageError) as ctx:
            app_page.build("no-such-app")
        self.assertEqual(ctx.exception.code, "not_found")
        if not app_page.is_enabled(app_page.find("zatgo-tracker")):
            with self.assertRaises(app_page.AppPageError) as ctx:
                app_page.build("zatgo-tracker")
            self.assertEqual(ctx.exception.code, "app_off")

    def test_a_user_without_access_gets_nothing(self) -> None:
        user = self._make("Employee")
        frappe.set_user(user)
        with self.assertRaises(app_page.AppPageError) as ctx:
            app_page.build("zatgo-vansalex")
        self.assertEqual(ctx.exception.code, "forbidden")

    def test_a_vansale_admin_sees_only_what_they_may_open(self) -> None:
        user = self._make("VanSale Admin")
        frappe.set_user(user)
        data = app_page.build("zatgo-vansalex")
        links = [link for s in data["overview"]["sections"] for link in s["links"]] + data["overview"]["shortcuts"]
        self.assertTrue(links)
        for link in links:
            if link["type"] == "DocType":
                self.assertTrue(frappe.has_permission(link["name"], "read"), f"{link['name']} offered without read access")
        self.assertFalse(data["can_manage"])  # switching apps stays a System Manager's call

    def test_the_api_wraps_the_page_in_the_standard_envelope(self) -> None:
        ok = api.get_app_page("zatgo-vansalex")
        self.assertTrue(ok["success"])
        self.assertIn("zg_app.css", ok["data"]["css"])
        missing = api.get_app_page("no-such-app")
        self.assertEqual((missing["success"], missing["error"]["code"]), (False, "not_found"))
        frappe.set_user("Guest")
        self.assertEqual(api.get_app_page("zatgo-vansalex")["error"]["code"], "forbidden")

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
