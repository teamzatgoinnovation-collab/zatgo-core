"""No seller VAT number -> no ZATCA QR, instead of a QR carrying a made-up all-zeros number."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.services import zatca_qr
from zatgo_core.tests.integration._fixtures import get_or_create_test_company


class _Doc(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


class TestZatcaSellerVat(IntegrationTestCase):
    def setUp(self) -> None:
        self.doc = _Doc(
            name="ZATCA-TEST-INV",
            company=get_or_create_test_company(),
            grand_total=115,
            total_taxes_and_charges=15,
            posting_date="2026-11-06",
            posting_time="10:00:00",
            is_return=0,
        )

    def test_no_vat_number_gives_no_qr(self) -> None:
        with patch.object(zatca_qr, "_seller_vat", return_value=""), patch.object(frappe.db, "set_value") as stored:
            self.assertEqual(zatca_qr.generate_and_store_zatca_qr(self.doc), "")
            self.assertEqual(zatca_qr.zatca_qr_data_uri(self.doc), "")
        stored.assert_not_called()

    def test_vat_number_is_encoded_as_is(self) -> None:
        with patch.object(zatca_qr, "_seller_vat", return_value="300000000000003"), patch.object(frappe.db, "set_value"):
            qr = zatca_qr.generate_and_store_zatca_qr(self.doc)
            self.assertTrue(zatca_qr.zatca_qr_data_uri(self.doc).startswith("data:image/png"))
        self.assertIn(b"300000000000003", base64.b64decode(qr))
