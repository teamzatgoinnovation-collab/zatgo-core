"""Chat event protocol — backend-agnostic envelopes for clients."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


EVENT_TYPES = (
	"thinking",
	"planning",
	"tool_started",
	"tool_progress",
	"tool_finished",
	"artifact_created",
	"assistant_message",
	"done",
	"error",
)


@dataclass
class ChatEvent:
	session: str
	type: str
	data: dict = field(default_factory=dict)
	ts: str = ""

	def __post_init__(self):
		if not self.ts:
			self.ts = datetime.now(timezone.utc).isoformat()
		if self.type not in EVENT_TYPES and self.type:
			# allow custom but prefer known
			pass

	def to_dict(self) -> dict:
		return {"session": self.session, "type": self.type, "ts": self.ts, "data": self.data or {}}


class EventPublisher:
	"""Publish chat_ai:event (+ legacy progress/stream when mapped)."""

	def __init__(self, session: str, *, enabled: bool = True):
		self.session = session
		self.enabled = enabled

	def emit(self, event_type: str, data: dict | None = None):
		evt = ChatEvent(session=self.session, type=event_type, data=data or {})
		if not self.enabled:
			return evt
		try:
			import frappe

			frappe.publish_realtime(
				"chat_ai:event",
				evt.to_dict(),
				user=frappe.session.user,
			)
		except Exception:
			pass
		return evt

	def planning(self, detail: str = ""):
		return self.emit("planning", {"detail": detail})

	def thinking(self, detail: str = ""):
		return self.emit("thinking", {"detail": detail})

	def tool_started(self, tool: str, detail: str = ""):
		return self.emit("tool_started", {"tool": tool, "detail": detail})

	def tool_progress(self, tool: str, detail: str = "", stage: str = ""):
		return self.emit("tool_progress", {"tool": tool, "detail": detail, "stage": stage})

	def tool_finished(self, tool: str, ok: bool = True, detail: str = ""):
		return self.emit("tool_finished", {"tool": tool, "ok": ok, "detail": detail})

	def artifact_created(self, artifact_id: str, artifact_type: str = "", title: str = ""):
		return self.emit(
			"artifact_created",
			{"artifact_id": artifact_id, "artifact_type": artifact_type, "title": title},
		)

	def assistant_message(self, chunk: str, done: bool = False):
		return self.emit("assistant_message", {"chunk": chunk, "done": done})

	def done(self, detail: str = ""):
		return self.emit("done", {"detail": detail})

	def error(self, message: str):
		return self.emit("error", {"message": message})


def map_progress_stage(stage: str) -> str:
	"""Map legacy progress stages to event types."""
	if stage in ("planning",):
		return "planning"
	if stage in ("done",):
		return "done"
	if stage in ("routing", "working"):
		return "thinking"
	return "tool_progress"
