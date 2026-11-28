"""F-5 / Phase 15: one version everywhere a release states it."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class TestReleaseIdentity(unittest.TestCase):
    def test_every_version_source_agrees(self) -> None:
        from zatgo_core import __version__
        from zatgo_core import hooks

        pyproject = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
        setup = re.search(r'version="([^"]+)"', (ROOT / "setup.py").read_text()).group(1)
        self.assertEqual({__version__, hooks.app_version, pyproject, setup}, {__version__})
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")
