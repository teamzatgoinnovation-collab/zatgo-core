"""Cache key formatting tests."""

from __future__ import annotations

import unittest


class TestCacheKeys(unittest.TestCase):
    def test_company_cache_key_format(self) -> None:
        from zatgo_core.constants.settings import CACHE_KEYS

        self.assertEqual(
            CACHE_KEYS["COMPANY"].format(company="Acme"),
            "zg_core:company_settings:Acme",
        )
        self.assertEqual(
            CACHE_KEYS["USER_PREFS"].format(user="admin@example.com"),
            "zg_core:user_preferences:admin@example.com",
        )


if __name__ == "__main__":
    unittest.main()
