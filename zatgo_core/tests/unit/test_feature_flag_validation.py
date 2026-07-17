"""Validation tests for feature flags."""

from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestFeatureFlagValidation(unittest.TestCase):
    def test_flag_key_rejects_invalid(self) -> None:
        mock_frappe = MagicMock()
        mock_frappe._ = lambda s: s
        mock_frappe.throw.side_effect = Exception("throw")

        with patch.dict("sys.modules", {"frappe": mock_frappe}):
            import zatgo_core.validation.feature_flags as mod

            importlib.reload(mod)
            doc = SimpleNamespace(
                flag_key="Bad Key",
                status="Enabled",
                rollout_percent=100,
            )
            with self.assertRaises(Exception):
                mod.validate_feature_flag(doc)

    def test_flag_key_accepts_valid(self) -> None:
        mock_frappe = MagicMock()
        mock_frappe._ = lambda s: s

        with patch.dict("sys.modules", {"frappe": mock_frappe}):
            import zatgo_core.validation.feature_flags as mod

            importlib.reload(mod)
            doc = SimpleNamespace(
                flag_key="zatgo.pos.split_payment",
                status="Enabled",
                rollout_percent=50,
            )
            mod.validate_feature_flag(doc)
            mock_frappe.throw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
