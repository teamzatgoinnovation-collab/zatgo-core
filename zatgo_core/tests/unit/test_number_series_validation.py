"""Validation tests for number series."""

from __future__ import annotations

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestNumberSeriesValidation(unittest.TestCase):
    def test_duplicate_document_type_rejected(self) -> None:
        mock_frappe = MagicMock()
        mock_frappe._ = lambda s: s
        mock_frappe.throw.side_effect = Exception("throw")

        with patch.dict("sys.modules", {"frappe": mock_frappe}):
            import zatgo_core.validation.number_series as mod

            importlib.reload(mod)
            row = SimpleNamespace(
                document_type="Sales Invoice",
                prefix="ZG-SINV-",
                padding=5,
            )
            doc = SimpleNamespace(series_items=[row, row])
            with self.assertRaises(Exception):
                mod.validate_number_series(doc)


if __name__ == "__main__":
    unittest.main()
