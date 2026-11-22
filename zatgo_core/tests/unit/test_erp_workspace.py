"""ZatGo ERP workspace (no database): the shipped Workspace file matches its source, the role is one string everywhere."""

from __future__ import annotations

import json
import os
import unittest

from zatgo_core.constants.roles import ROLES
from zatgo_core.services import erp_workspace

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
