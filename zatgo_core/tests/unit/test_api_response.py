"""Unit tests for API response envelope."""

from __future__ import annotations

import importlib
import unittest
from unittest.mock import MagicMock, patch


class TestApiResponse(unittest.TestCase):
    def test_ok_envelope(self) -> None:
        with patch.dict("sys.modules", {"frappe": MagicMock()}):
            import zatgo_core.api.response as response_mod

            importlib.reload(response_mod)
            payload = response_mod.ok({"brand_name": "ZatGo"}, meta={"source": "test"})
            self.assertTrue(payload["success"])
            self.assertEqual(payload["data"]["brand_name"], "ZatGo")
            self.assertIsNone(payload["error"])
            self.assertEqual(payload["meta"]["source"], "test")
            self.assertTrue(payload["request_id"])

    def test_fail_envelope(self) -> None:
        mock_frappe = MagicMock()
        with patch.dict("sys.modules", {"frappe": mock_frappe}):
            import zatgo_core.api.response as response_mod

            importlib.reload(response_mod)
            payload = response_mod.fail("FORBIDDEN", "Not allowed", details={"x": 1})
            self.assertFalse(payload["success"])
            self.assertEqual(payload["error"]["code"], "FORBIDDEN")
            self.assertIsNone(payload["data"])

    def test_paginated_envelope(self) -> None:
        with patch.dict("sys.modules", {"frappe": MagicMock()}):
            import zatgo_core.api.response as response_mod

            importlib.reload(response_mod)
            payload = response_mod.paginated(
                [1, 2], page=2, page_size=10, total=20, request_id="req-3"
            )
            self.assertTrue(payload["success"])
            self.assertEqual(payload["data"], [1, 2])
            self.assertEqual(payload["meta"]["page"], 2)
            self.assertEqual(payload["meta"]["page_size"], 10)
            self.assertEqual(payload["meta"]["total"], 20)
            self.assertEqual(payload["request_id"], "req-3")


if __name__ == "__main__":
    unittest.main()
