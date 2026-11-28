"""Phase 14: a fresh install refuses a site where another app owns one of ZatGo's DocType names."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core import install


class TestInstallGuard(IntegrationTestCase):
    def test_our_doctypes_are_found_and_none_clash_here(self) -> None:
        names = install.our_doctype_names()
        self.assertIn("Module Settings", names)
        self.assertGreater(len(names), 50)
        self.assertEqual(install.doctype_name_collisions(), [])

    def test_a_name_owned_by_another_app_is_refused(self) -> None:
        with patch.object(install, "our_doctype_names", return_value=["Module Settings", "User"]):
            self.assertEqual(install.doctype_name_collisions(), [("User", "frappe")])
            with self.assertRaises(frappe.ValidationError) as ctx:
                install._refuse_doctype_name_collisions()
        self.assertIn("User (owned by frappe)", str(ctx.exception))
