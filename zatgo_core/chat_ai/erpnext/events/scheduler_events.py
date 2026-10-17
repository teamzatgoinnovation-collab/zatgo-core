"""Scheduler jobs for chat_ai."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, now_datetime, today


def tick():
	"""Each scheduler tick: queue due ZatGo AI scheduled tasks (cheap: one indexed query)."""
	try:
		from zatgo_core.chat_ai.erpnext.scheduled_tasks import run_due

		run_due()
	except Exception:
		frappe.log_error(title="chat_ai scheduled tasks tick")


def hourly():
	_ping_provider()
	_ping_connectors()


def daily():
	_purge_old_conversations()


def _ping_connectors():
	try:
		from zatgo_core.chat_ai.core.tool_sources.health import check_all_connectors

		check_all_connectors()
	except Exception:
		frappe.log_error(title="chat_ai connector health")


def _ping_provider():
	try:
		from zatgo_core.chat_ai.erpnext.settings import get_settings_dict
		from zatgo_core.chat_ai.core.providers.registry import from_settings

		settings = get_settings_dict()
		provider = from_settings(settings)
		ok, latency, err = provider.ping()
		doc = frappe.get_doc(
			{
				"doctype": "AI Provider Health Log",
				"provider": settings.get("provider") or provider.name,
				"ok": 1 if ok else 0,
				"latency_ms": latency,
				"error": err,
				"capabilities_json": frappe.as_json(provider.capabilities.as_dict()),
				"checked_at": now_datetime(),
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(title="chat_ai provider health")


def _purge_old_conversations():
	try:
		days = int(frappe.db.get_single_value("Chat AI Settings", "conversation_retention_days") or 90)
		if days <= 0:
			return
		cutoff = add_days(today(), -days)
		sessions = frappe.get_all(
			"AI Chat Session",
			filters={"modified": ("<", cutoff), "is_pinned": 0},
			pluck="name",
			limit=200,
		)
		from zatgo_core.chat_ai.erpnext.sessions import purge_session

		for name in sessions:
			purge_session(name)
	except Exception:
		frappe.log_error(title="chat_ai retention purge")
