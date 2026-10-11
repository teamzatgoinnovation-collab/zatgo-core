"""ZATCA Phase 1 QR TLV encoding (services/zatca_qr.py)."""

from __future__ import annotations

import base64
import unittest

import frappe

from zatgo_core.services.zatca_qr import _invoice_timestamp, _tlv, build_zatca_tlv_base64


def _decode(b64: str) -> dict[int, str]:
    raw = base64.b64decode(b64)
    out, i = {}, 0
    while i < len(raw):
        tag, length = raw[i], raw[i + 1]
        out[tag] = raw[i + 2 : i + 2 + length].decode("utf-8")
        i += 2 + length
    return out


class TestZatcaQr(unittest.TestCase):
    def test_round_trip_of_the_five_fields(self) -> None:
        fields = _decode(
            build_zatca_tlv_base64(
                seller_name="شركة زاتجو",
                vat_number="300000000000003",
                timestamp="2026-10-11T09:11:15",
                invoice_total=115,
                vat_amount=15,
            )
        )
        self.assertEqual(
            fields,
            {1: "شركة زاتجو", 2: "300000000000003", 3: "2026-10-11T09:11:15", 4: "115.00", 5: "15.00"},
        )

    def test_timestamp_has_whole_seconds(self) -> None:
        doc = frappe._dict(posting_date="2026-10-11", posting_time="09:11:15.360562")
        self.assertEqual(_invoice_timestamp(doc), "2026-10-11T09:11:15")

    def test_overlong_value_is_cut_at_a_whole_character(self) -> None:
        name = "شركة" * 100  # 800 bytes of 2-byte letters
        field = _tlv(1, name)
        self.assertEqual(field[0], 1)
        self.assertLessEqual(field[1], 255)
        field[2:].decode("utf-8")  # still valid UTF-8 -- no half letter
        self.assertEqual(len(field), 2 + field[1])
