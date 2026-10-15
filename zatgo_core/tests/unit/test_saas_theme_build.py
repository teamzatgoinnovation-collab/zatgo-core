"""The served saas_theme.css is generated from css/src/*.css (scripts/build_saas_theme.py)."""

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build_saas_theme.py"


def _load():
	spec = importlib.util.spec_from_file_location("build_saas_theme", SCRIPT)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


class TestSaasThemeBuild(unittest.TestCase):
	def test_committed_css_matches_partials(self):
		if not SCRIPT.exists():  # packaged install without the repo's scripts/
			self.skipTest("build script not shipped")
		mod = _load()
		self.assertEqual(
			mod.OUT.read_text(encoding="utf-8"),
			mod.build(),
			"saas_theme.css is stale — run scripts/build_saas_theme.py and commit it",
		)
