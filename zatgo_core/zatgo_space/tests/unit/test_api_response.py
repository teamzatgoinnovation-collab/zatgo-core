"""Unit tests for API response helpers."""

from __future__ import annotations

import unittest

from zatgo_core.zatgo_space.api.response import fail, ok, paginated


class TestApiResponse(unittest.TestCase):
    def test_ok_envelope(self) -> None:
        payload = ok({"id": 1}, meta={"page": 1}, request_id="req-1")
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["id"], 1)
        self.assertEqual(payload["request_id"], "req-1")
        self.assertIsNone(payload["error"])

    def test_fail_envelope(self) -> None:
        payload = fail("E001", "Broken", details={"field": "x"}, request_id="req-2")
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "E001")

    def test_paginated_meta(self) -> None:
        payload = paginated([1, 2], page=2, page_size=10, total=20, request_id="req-3")
        self.assertEqual(payload["meta"]["page"], 2)
        self.assertEqual(payload["meta"]["total"], 20)
