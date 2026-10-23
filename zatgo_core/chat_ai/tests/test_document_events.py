"""The Chat AI document hook must not index the index (it fires on every DocType's insert/update)."""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

import frappe

from zatgo_core.chat_ai.erpnext.events import document_events


class TestReindexHook(TestCase):
	def _run(self, doctype: str, flags: dict[str, int]) -> int:
		doc = frappe._dict(doctype=doctype, name="X")
		with patch.object(
			frappe.db, "get_single_value", side_effect=lambda dt, field: flags.get(field, 0)
		), patch.object(frappe, "enqueue") as enqueue:
			document_events.after_insert(doc)
			document_events.on_update(doc)
		return enqueue.call_count

	def test_an_ordinary_document_is_queued_for_indexing(self) -> None:
		both = {"enable_document_events": 1, "enable_vector_search": 1}
		self.assertEqual(self._run("Sales Invoice", both), 2)

	def test_the_index_itself_and_log_tables_are_not(self) -> None:
		both = {"enable_document_events": 1, "enable_vector_search": 1}
		for doctype in ("AI Search Index", "AI Tool Log", "Error Log", "Version", "Comment"):
			self.assertEqual(self._run(doctype, both), 0, doctype)

	def test_nothing_is_queued_unless_both_switches_are_on(self) -> None:
		self.assertEqual(self._run("Sales Invoice", {"enable_document_events": 1}), 0)
		self.assertEqual(self._run("Sales Invoice", {"enable_vector_search": 1}), 0)
