"""ZatGo ERP workspace (no database): the shipped Workspace file matches its source, the role is one string everywhere."""

from __future__ import annotations

import json
import os
import unittest

from zatgo_core.constants.roles import ROLES
from zatgo_core.services import erp_summary, erp_workspace

PACKAGE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WS_FILE = os.path.join(PACKAGE, "zatgo_core", "workspace", "zatgo_erp", "zatgo_erp.json")


class TestErpWorkspace(unittest.TestCase):
    def test_file_is_generated_from_sections(self):
        """Run scripts/build_zatgo_erp_workspace.py after editing SECTIONS."""
        with open(WS_FILE) as f:
            shipped = json.load(f)
        self.assertEqual(shipped, json.loads(json.dumps(erp_workspace.workspace_json())))

    def test_role_is_one_string(self):
        self.assertEqual(erp_workspace.ROLE, ROLES["ACCOUNTS_INVENTORY"])
        self.assertIn(erp_workspace.ROLE, erp_workspace.ROLES)

    def test_reports_name_their_doctype_and_shortcuts_are_listed(self):
        listed = {i["link_to"] for _l, _i, items in erp_workspace.SECTIONS for i in items}
        for _label, _icon, items in erp_workspace.SECTIONS:
            for item in items:
                if item["link_type"] == "Report":
                    self.assertTrue(item.get("ref_doctype"), item["label"])
        for shortcut in erp_workspace.SHORTCUTS:
            self.assertIn(shortcut, listed)

    def test_layout_groups(self):
        self.assertEqual([s[0] for s in erp_workspace.SECTIONS], ["Transactions", "Setup", "Reports", "Settings"])

    def test_summary_tiles_follow_the_shortcut_order(self):
        self.assertEqual([d for d, _field in erp_summary.DOCS], list(erp_workspace.SHORTCUTS))

    def test_workspace_points_at_the_summary_block_and_its_files_exist(self):
        with open(WS_FILE) as f:
            shipped = json.load(f)
        self.assertEqual([b["custom_block_name"] for b in shipped["custom_blocks"]], [erp_workspace.BLOCK_NAME])
        self.assertIn("custom_block", [b["type"] for b in json.loads(shipped["content"])])
        for name in ("block.html", "block.js", "block.css"):
            self.assertTrue(os.path.exists(os.path.join(PACKAGE, "templates", "erp_summary", name)), name)

    def test_dashboard_file_is_generated_and_has_its_own_name(self):
        path = os.path.join(PACKAGE, "zatgo_core", "zatgo_core_dashboard", "zatgo_erp_dashboard", "zatgo_erp_dashboard.json")
        with open(path) as f:
            shipped = json.load(f)
        self.assertEqual(shipped, json.loads(json.dumps(erp_workspace.dashboard_json())))
        # a Dashboard named like an existing Workspace Sidebar (e.g. "Accounts") would switch the sidebar away
        self.assertNotIn(erp_workspace.DASHBOARD, ("Accounts", "Stock", "Selling", "Buying"))

    def test_standard_erpnext_roles_see_the_workspace_too(self):
        for role in ("System Manager", "Accounts User", "Sales User", "Purchase User", "Stock User"):
            self.assertIn(role, erp_workspace.ROLES)
        self.assertEqual(erp_workspace.ROLES[0], erp_workspace.ROLE)

    def test_dashboard_shortcut_is_in_the_workspace_file_and_its_page_content(self):
        with open(WS_FILE) as f:
            shipped = json.load(f)
        self.assertIn(("Dashboard", erp_workspace.DASHBOARD), [(s["type"], s["link_to"]) for s in shipped["shortcuts"]])
        blocks = json.loads(shipped["content"])
        # the editor deletes a shortcut no content block shows
        self.assertTrue(any(b["type"] == "shortcut" and b["data"]["shortcut_name"] == "Dashboard" for b in blocks))

    def test_number_cards_are_files_and_on_the_dashboard(self):
        import re

        for label, doctype, function, field in erp_workspace.NUMBER_CARDS:
            slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
            path = os.path.join(PACKAGE, "zatgo_core", "number_card", slug, f"{slug}.json")
            with open(path) as f:
                self.assertEqual(json.load(f), json.loads(json.dumps(erp_workspace.number_card_json(label, doctype, function, field))))
            self.assertIn(label, erp_workspace.DASHBOARD_CARDS)

    def test_app_dict_describes_zatgo_erp_for_the_sidebar_builder(self):
        app = erp_workspace.app_dict()
        self.assertEqual(app["workspaces"], (erp_workspace.NAME,))
        self.assertEqual(app["overview_label"], "Home")
        self.assertEqual(set(app["group_icons"]), {s[0] for s in erp_workspace.SECTIONS})
