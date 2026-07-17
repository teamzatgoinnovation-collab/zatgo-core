"""Smoke tests for package importability."""

from __future__ import annotations

import unittest


class TestAppImport(unittest.TestCase):
    def test_package_version(self) -> None:
        import zatgo_core

        self.assertEqual(zatgo_core.__version__, "0.2.0")

    def test_constants_export(self) -> None:
        from zatgo_core.constants import DOCTYPES, ROLES

        self.assertEqual(DOCTYPES["SYSTEM_SETTINGS"], "ZG System Settings")
        self.assertIn("ZG Company Admin", ROLES.values())


if __name__ == "__main__":
    unittest.main()
