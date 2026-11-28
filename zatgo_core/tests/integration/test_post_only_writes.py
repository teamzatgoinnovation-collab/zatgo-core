"""S-03 (Phase 12): endpoints that write accept POST only, so a crafted link (GET, no CSRF check) cannot change data."""

from __future__ import annotations

import importlib

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

WRITES = (
    "zatgo_core.api.v1.accounting.invoices.create",
    "zatgo_core.api.v1.accounting.invoices.submit",
    "zatgo_core.api.v1.accounting.payments.create_receive",
    "zatgo_core.api.v1.accounting.journals.create",
    "zatgo_core.api.v1.vansalex.orders.create",
    "zatgo_core.api.v1.vansalex.stock.transfer",
    "zatgo_core.api.v1.settings.save_settings",
    "zatgo_core.chat_ai.api.chat.send",
)
READS = ("zatgo_core.api.v1.accounting.invoices.list", "zatgo_core.api.v1.accounting.invoices.get")


def _fn(path: str):
    module, name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)


class TestPostOnlyWrites(IntegrationTestCase):
    def test_writes_refuse_get(self) -> None:
        for path in WRITES:
            self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func.get(_fn(path)), ["POST"], path)

    def test_reads_still_accept_get(self) -> None:
        for path in READS:
            self.assertIn("GET", frappe.allowed_http_methods_for_whitelisted_func.get(_fn(path), ["GET"]), path)
