"""App catalog resilience (no database): one module's broken app_manifest.py
must never stop the catalog -- ui_apps imports it, so an exception here would
break every request on every site."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from zatgo_core import __version__
from zatgo_core.services import app_catalog

GOOD = '''APP = {"key": "good_mod", "label": "Good", "group": "bundled", "module_def": "Good Mod",
       "switch_field": "enable_good_mod", "settings": (("Good Settings", "Good Settings"),)}\n'''


class TestAppCatalogResilience(unittest.TestCase):
    def _build(self, modules: dict[str, str]):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for folder, source in modules.items():
            os.makedirs(os.path.join(tmp.name, folder))
            with open(os.path.join(tmp.name, folder, "app_manifest.py"), "w") as f:
                f.write(source)
        self.addCleanup(app_catalog.catalog.cache_clear)
        app_catalog.catalog.cache_clear()
        with patch.object(app_catalog, "PACKAGE_DIR", tmp.name):
            return app_catalog.catalog(), app_catalog.load_errors()

    def test_real_catalog_loads_clean(self) -> None:
        app_catalog.catalog.cache_clear()
        self.assertEqual(app_catalog.load_errors(), [])
        keys = {a["key"] for a in app_catalog.catalog()}
        self.assertTrue({"chat_ai", "tracker", "zatgo_space", "saas_theme"} <= keys)

    def test_syntax_error_is_skipped_not_raised(self) -> None:
        apps, errors = self._build({"good_mod": GOOD, "broken": "APP = {"})
        keys = {a["key"] for a in apps}
        self.assertIn("good_mod", keys)
        self.assertEqual(len(errors), 1)
        self.assertIn("broken/app_manifest.py", errors[0])

    def test_missing_key_and_unknown_group_are_skipped(self) -> None:
        apps, errors = self._build(
            {
                "good_mod": GOOD,
                "nokey": 'APP = {"label": "x", "group": "bundled", "module_def": "X"}\n',
                "badgroup": 'APP = {"key": "bg", "label": "x", "group": "nope"}\n',
                "noapp": "X = 1\n",
            }
        )
        self.assertIn("good_mod", {a["key"] for a in apps})
        self.assertEqual(len(errors), 3)

    def test_duplicate_key_keeps_the_first(self) -> None:
        apps, errors = self._build({"a_mod": GOOD, "b_mod": GOOD})
        self.assertEqual([a["folder"] for a in apps if a["key"] == "good_mod"], ["a_mod"])
        self.assertEqual(len(errors), 1)
        self.assertIn("duplicate", errors[0])

    def test_broken_module_leaves_no_switch(self) -> None:
        apps, _ = self._build({"broken": "APP = {"})
        self.assertFalse(any(a["switch_field"] == "enable_broken" for a in apps))

class TestManifestContract(unittest.TestCase):
    """Manifest v2: every new key is optional, bad values are rejected at load (and skipped, never raised
    into a request -- see TestAppCatalogResilience)."""

    def _norm(self, **kw):
        return app_catalog._normalise({"key": "x", "label": "X", "group": "core", **kw}, "test")

    def test_a_minimal_manifest_gets_sane_defaults(self) -> None:
        app = self._norm()
        self.assertEqual(app["version"], __version__)
        self.assertEqual((app["requires"], app["api_prefixes"], app["workspaces"], app["settings"]), ((), (), (), ()))
        self.assertIsNone(app["switch_field"])
        self.assertFalse(app["default_on"])

    def test_a_bundled_module_always_has_a_switch(self) -> None:
        app = self._norm(group="bundled", module_def="X Mod")
        self.assertEqual(app["switch_field"], "enable_x")
        self.assertEqual(self._norm(group="bundled", module_def="X Mod", switch_field="enable_other")["switch_field"], "enable_other")

    def test_api_prefixes_must_end_with_a_dot(self) -> None:
        # "zatgo_core.api.v1.vansalex" would also gate "...vansalex_extra"; the dot makes it a package.
        self.assertEqual(self._norm(api_prefixes=("a.b.",))["api_prefixes"], ("a.b.",))
        with self.assertRaises(ValueError):
            self._norm(api_prefixes=("a.b",))

    def test_requires_and_prefixes_are_lists_of_strings(self) -> None:
        for bad in ("tracker", ("ok", ""), (1,)):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self._norm(requires=bad)

    def test_dependency_problems_name_the_missing_requirement(self) -> None:
        apps = (
            self._norm(key="base", label="Base", switch_field="enable_base"),
            self._norm(key="addon", label="Add-on", switch_field="enable_addon", requires=("base",)),
            self._norm(key="plain", label="Plain", requires=("base",)),  # no switch: always on
        )
        with patch.object(app_catalog, "catalog", return_value=apps):
            self.assertEqual(app_catalog.dependency_problems({"base": True, "addon": True}), [])
            self.assertEqual(app_catalog.dependency_problems({"base": False, "addon": False}), ["Plain needs Base to be on"])
            self.assertEqual(
                app_catalog.dependency_problems({"base": False, "addon": True}),
                ["Add-on needs Base to be on", "Plain needs Base to be on"],
            )

    def test_the_real_catalog(self) -> None:
        app_catalog.catalog.cache_clear()
        self.assertEqual(app_catalog.load_errors(), [])
        prefixes = app_catalog.api_prefixes()
        # A bundled module is gated at its current path and its old app's.
        self.assertEqual(set(prefixes["chat_ai"]), {"zatgo_core.chat_ai.", "chat_ai."})
        self.assertEqual(prefixes["vansalex"], ("zatgo_core.api.v1.vansalex.",))
        vansalex = app_catalog.get("vansalex")
        self.assertTrue(vansalex["default_on"])
        self.assertEqual(vansalex["switch_field"], "enable_vansalex")
        self.assertEqual(app_catalog.get("vansalex_web")["requires"], ("vansalex",))
        self.assertIn("VanSaleX Settings", app_catalog.settings_doctypes())
        # Every switch field is unique.
        fields = [a["switch_field"] for a in app_catalog.catalog() if a["switch_field"]]
        self.assertEqual(len(fields), len(set(fields)))


if __name__ == "__main__":
    unittest.main()
