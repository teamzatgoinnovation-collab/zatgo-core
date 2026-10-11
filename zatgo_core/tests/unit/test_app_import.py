"""Smoke tests for package importability."""

from __future__ import annotations

import unittest


class TestAppImport(unittest.TestCase):
    def test_package_version(self) -> None:
        import zatgo_core

        # The package version is set in zatgo_core/__init__.py; just check it
        # is a real dotted version (was a hard-coded stale "0.2.0").
        self.assertRegex(zatgo_core.__version__, r"^\d+\.\d+\.\d+$")

    def test_constants_export(self) -> None:
        from zatgo_core.constants import DOCTYPES, ROLES

        self.assertEqual(DOCTYPES["SYSTEM_SETTINGS"], "ZG System Settings")
        self.assertIn("ZG Company Admin", ROLES.values())


if __name__ == "__main__":
    unittest.main()
