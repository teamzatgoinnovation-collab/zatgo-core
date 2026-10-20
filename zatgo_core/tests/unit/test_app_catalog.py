"""App catalog resilience (no database): one module's broken app_manifest.py
must never stop the catalog -- ui_apps imports it, so an exception here would
break every request on every site."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

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

if __name__ == "__main__":
    unittest.main()
