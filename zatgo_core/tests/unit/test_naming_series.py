"""Return-series resolution: pure logic, no frappe needed.

Loaded by file path (not `import zatgo_core.services.naming_series`) because
the `zatgo_core.services` package's __init__ eagerly imports controllers that
need real frappe submodules -- a bare mock of "frappe" isn't enough for that
chain, but this module itself only does a plain `import frappe`.
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import MagicMock, patch


def _load_naming_series_module():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "services", "naming_series.py")
    with patch.dict("sys.modules", {"frappe": MagicMock()}):
        spec = importlib.util.spec_from_file_location("_naming_series_under_test", os.path.abspath(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


resolve_series_for_return_state = _load_naming_series_module().resolve_series_for_return_state


class TestResolveSeriesForReturnState(unittest.TestCase):
    def test_return_switches_plain_series_to_ret_counterpart(self) -> None:
        result = resolve_series_for_return_state("SINV-", ["SINV-", "SINV-RET-"], is_return=True)
        self.assertEqual(result, "SINV-RET-")

    def test_return_switches_dated_series_to_ret_counterpart(self) -> None:
        options = ["ACC-PINV-.YYYY.-", "ACC-PINV-RET-.YYYY.-"]
        result = resolve_series_for_return_state("ACC-PINV-.YYYY.-", options, is_return=True)
        self.assertEqual(result, "ACC-PINV-RET-.YYYY.-")

    def test_non_return_switches_ret_series_back_to_plain(self) -> None:
        result = resolve_series_for_return_state("SINV-RET-", ["SINV-", "SINV-RET-"], is_return=False)
        self.assertEqual(result, "SINV-")

    def test_already_consistent_return_is_untouched(self) -> None:
        result = resolve_series_for_return_state("SINV-RET-", ["SINV-", "SINV-RET-"], is_return=True)
        self.assertIsNone(result)

    def test_already_consistent_non_return_is_untouched(self) -> None:
        result = resolve_series_for_return_state("SINV-", ["SINV-", "SINV-RET-"], is_return=False)
        self.assertIsNone(result)

    def test_no_configured_counterpart_is_untouched(self) -> None:
        result = resolve_series_for_return_state("CUSTOM-SERIES-", ["CUSTOM-SERIES-"], is_return=True)
        self.assertIsNone(result)

    def test_empty_current_is_untouched(self) -> None:
        result = resolve_series_for_return_state("", ["SINV-", "SINV-RET-"], is_return=True)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
