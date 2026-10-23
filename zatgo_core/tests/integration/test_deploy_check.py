"""setup/deploy_check.py: the read-only post-migrate check used by the Hetzner deploy script."""

from __future__ import annotations

import copy

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.setup import deploy_check


class TestDeployCheck(IntegrationTestCase):
    def test_a_migrated_site_passes(self) -> None:
        checks = deploy_check.collect()
        self.assertTrue(deploy_check.verdict(checks), frappe.as_json(checks))

    def test_the_check_only_reads(self) -> None:
        tables = ("tabPatch Log", "tabSingles", "tabZG Registered Application", "tabCustom Field")
        before = {t: frappe.db.sql(f"select count(*) from `{t}`")[0][0] for t in tables}
        deploy_check.collect()
        self.assertEqual({t: frappe.db.sql(f"select count(*) from `{t}`")[0][0] for t in tables}, before)

    def test_each_blocking_problem_fails_the_verdict(self) -> None:
        good = deploy_check.collect()
        self.assertTrue(deploy_check.verdict(good))
        broken = {
            "settings_has_enable_vansalex": False,
            "warehouse_transfer_point_column": False,
            "vansalex_settings_has_max_adjust_qty": False,
            "patches_logged": {**good["patches_logged"], deploy_check.RELEASE_PATCHES[0]: False},
            "missing_indexes": ["tabZG Trip.status"],
            "enable_vansalex_stored": None,
            "app_manifest_errors": ["x/app_manifest.py: boom"],
            "registry_bad_category": ["tracker"],
            "zatgo_sidebar_exists": False,
            "hub_page_exists": False,
            "staff_only_doctypes_grant_all": ["ZG Order"],
        }
        for key, value in broken.items():
            bad = copy.deepcopy(good)
            bad[key] = value
            self.assertFalse(deploy_check.verdict(bad), key)
        # informational only
        info = copy.deepcopy(good)
        info["staff_only_doctypes_with_custom_docperm"] = ["ZG Delivery Stop"]
        self.assertTrue(deploy_check.verdict(info))
