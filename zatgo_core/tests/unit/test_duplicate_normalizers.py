"""Pure tests for services/duplicate/normalizers.py (no database)."""

from __future__ import annotations

import unittest

from zatgo_core.services.duplicate import normalizers as n


class TestNormalizers(unittest.TestCase):
    def test_phone_formats_of_one_number_agree(self):
        forms = ["+966 50 000 0000", "00966500000000", "0500000000", "500000000", "966500000000", "+966-50-000-0000", "٠٥٠٠٠٠٠٠٠٠"]
        self.assertEqual({n.phone(f) for f in forms}, {"966500000000"})

    def test_other_country_code_is_preserved(self):
        self.assertEqual(n.phone("+971 50 123 4567"), "971501234567")
        self.assertNotEqual(n.phone("+971 50 123 4567"), n.phone("0501234567"))

    def test_phone_variants_cover_stored_spellings(self):
        variants = n.phone_variants("0500000000")
        for stored in ("+966500000000", "966500000000", "0500000000", "500000000"):
            self.assertIn(stored, variants)

    def test_email_is_trimmed_and_lowercased(self):
        self.assertEqual(n.email("  Sales@ABC-Trading.COM "), "sales@abc-trading.com")

    def test_tax_id_drops_separators_and_arabic_digits(self):
        self.assertEqual(n.tax_id("310-000 000 000 003"), "310000000000003")
        self.assertEqual(n.tax_id("٣١٠٠٠٠٠٠٠٠٠٠٠٠٣"), "310000000000003")
        self.assertEqual(n.tax_id("ab-12"), "AB12")

    def test_code_keeps_every_character(self):
        self.assertEqual(n.code("  AB-12/x.3 "), "AB-12/x.3")

    def test_arabic_name_folding(self):
        self.assertEqual(n.name("أَحمد  مؤسسة"), n.name("احمد مؤسسه"))
        self.assertEqual(n.name("ABC  Trading"), n.name("abc trading"))

    def test_similarity(self):
        self.assertGreaterEqual(n.similarity(n.name("ABC Trading"), n.name("ABC Tradng")), 0.85)
        self.assertLess(n.similarity(n.name("ABC Trading"), n.name("Xyz Industries")), 0.5)
