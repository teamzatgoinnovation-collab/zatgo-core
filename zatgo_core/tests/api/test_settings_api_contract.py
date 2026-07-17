"""API contract tests (import / whitelist presence)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


class TestSettingsApiContract(unittest.TestCase):
    def test_settings_api_whitelists_expected_methods(self) -> None:
        path = Path(__file__).resolve().parents[2] / "api" / "v1" / "settings.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        expected = {
            "get_system_settings",
            "get_company_settings",
            "get_branch_settings",
            "get_user_preferences",
            "save_settings",
            "reload_settings",
            "clear_cache",
        }
        self.assertTrue(expected.issubset(functions))


if __name__ == "__main__":
    unittest.main()
