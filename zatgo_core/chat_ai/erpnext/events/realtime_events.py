"""Realtime progress / stream helpers + chat_ai:event dual publish."""

from __future__ import annotations

import frappe

from zatgo_core.chat_ai.core.events import EventPublisher, map_progress_stage

STAGE_LABELS = {
	"searching": "Searching...",
	"reading_erp": "Reading ERP...",
	"running_workflow": "Running Workflow...",
	"generating_report": "Generating Report...",
	"creating_document": "Creating Document...",
	"planning": "Planning...",
	"routing": "Routing...",
	"done": "Done",
	"working": "Working...",
}


def _publisher(session: str) -> EventPublisher:
	enabled = True
	try:
		enabled = bool(frappe.db.get_single_value("Chat AI Settings", "enable_event_stream") or 1)
	except Exception:
		enabled = True
	return EventPublisher(session, enabled=enabled)


def publish_progress(session: str, stage: str, detail: str = "", tool: str = ""):
	label = STAGE_LABELS.get(stage, STAGE_LABELS["working"])
	frappe.publish_realtime(
		"chat_ai:progress",
		{"session": session, "stage": stage, "label": label, "detail": detail, "tool": tool},
		user=frappe.session.user,
	)
	pub = _publisher(session)
	etype = map_progress_stage(stage)
	if etype == "planning":
		pub.planning(detail or label)
	elif etype == "done":
		pub.done(detail or label)
	elif etype == "thinking":
		pub.thinking(detail or label)
	else:
		pub.tool_progress(tool or detail or "", detail or label, stage)


def publish_stream(session: str, chunk: str, done: bool = False):
	frappe.publish_realtime(
		"chat_ai:stream",
		{"session": session, "chunk": chunk, "done": done},
		user=frappe.session.user,
	)
	_publisher(session).assistant_message(chunk or "", done=done)


def publish_typed_stream(session: str, text: str, *, chunk_size: int = 6):
	"""Publish full text as word-sized chunks so Desk can type ChatGPT-style."""
	import re

	text = text or ""
	if not text:
		publish_stream(session, "", done=True)
		return
	# Prefer whole words; fall back to small character groups
	parts = re.findall(r"\s+|[^\s]+", text)
	if not parts:
		step = max(1, int(chunk_size or 6))
		parts = [text[i : i + step] for i in range(0, len(text), step)]
	for part in parts:
		publish_stream(session, part, done=False)
	publish_stream(session, "", done=True)


def publish_notify(title: str, message: str, user: str | None = None):
	frappe.publish_realtime(
		"chat_ai:notify",
		{"title": title, "message": message},
		user=user or frappe.session.user,
	)


def publish_event(session: str, event_type: str, data: dict | None = None):
	return _publisher(session).emit(event_type, data or {})
