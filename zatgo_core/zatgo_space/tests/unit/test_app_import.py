"""Smoke tests proving the ZatGo Space module imports cleanly (a module of
zatgo_core since the zatgo_space app was merged in)."""

from __future__ import annotations

import unittest

import frappe


class TestAppImport(unittest.TestCase):
    """Basic install / import checks."""

    def test_module_belongs_to_zatgo_core(self) -> None:
        self.assertIn("zatgo_core", frappe.get_installed_apps())
        self.assertIn("ZatGo Space", frappe.get_module_list("zatgo_core"))

    def test_version_defined(self) -> None:
        from zatgo_core.zatgo_space import __version__

        self.assertTrue(__version__)
