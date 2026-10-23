"""Document events — gated by Chat AI Settings."""

from __future__ import annotations

import frappe


def _enabled() -> bool:
	try:
		return bool(frappe.db.get_single_value("Chat AI Settings", "enable_document_events"))
	except Exception:
		return False


def after_insert(doc, method=None):
	_maybe_reindex(doc)


def on_update(doc, method=None):
	_maybe_reindex(doc)


def on_submit(doc, method=None):
	_maybe_notify(doc, "submitted")


def on_cancel(doc, method=None):
	_maybe_notify(doc, "cancelled")


# Indexing writes AI Search Index rows, and this hook runs on every DocType's insert/update: indexing the
# index (or Chat AI's own log-like tables, or Frappe's) would queue another job for each one it writes.
NOT_INDEXED = frozenset(
	{
		"AI Search Index",
		"AI Tool Log",
		"AI Usage Daily",
		"AI Provider Health Log",
		"AI Chat Message",
		"Error Log",
		"Scheduled Job Log",
		"Activity Log",
		"Access Log",
		"Version",
		"Comment",
	}
)


def indexable(doctype: str) -> bool:
	return doctype not in NOT_INDEXED


def _maybe_reindex(doc):
	if not _enabled() or not indexable(doc.doctype):
		return
	try:
		if not frappe.db.get_single_value("Chat AI Settings", "enable_vector_search"):
			return
		# enqueue lightweight stub — indexer may expand later
		frappe.enqueue(
			"zatgo_core.chat_ai.erpnext.search.indexer.index_document",
			doctype=doc.doctype,
			name=doc.name,
			queue="short",
			enqueue_after_commit=True,
		)
	except Exception:
		pass


def _maybe_notify(doc, action: str):
	try:
		if not frappe.db.get_single_value("Chat AI Settings", "enable_chat_notifications"):
			return
		from zatgo_core.chat_ai.erpnext.events.realtime_events import publish_notify

		publish_notify(doc.doctype, f"{doc.name} was {action}")
	except Exception:
		pass
