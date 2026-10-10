"""Background turn / report jobs."""

from __future__ import annotations

_HEAVY_HINTS = (
	"company status",
	"business overview",
	"dashboard",
	"full report",
	"export",
	"bulk",
	"all companies",
	"aging",
)


def should_run_background(message: str, settings: dict | None = None, execution_mode: str | None = None) -> bool:
	settings = settings or {}
	mode = (execution_mode or "immediate").lower()
	if mode == "_worker":
		return False
	if mode == "background":
		return bool(settings.get("enable_background_turns") or settings.get("enable_background_jobs"))
	# "scheduled" is an explicit opt-in (managers only — gated in orchestrator).
	if mode == "scheduled":
		return bool(settings.get("enable_background_turns") or settings.get("enable_background_jobs"))
	# Heuristic path only when background turns explicitly enabled
	if not settings.get("enable_background_turns"):
		return False
	msg = (message or "").lower()
	return any(h in msg for h in _HEAVY_HINTS)


def enqueue_turn(**kwargs):
	"""Enqueue run_turn in background; returns job id-ish dict."""
	import frappe

	frappe.enqueue(
		"zatgo_core.chat_ai.erpnext.jobs.turn_jobs.execute_turn",
		queue="long",
		timeout=600,
		**kwargs,
	)
	return {"queued": True, "execution_mode": "background"}


def execute_turn(**kwargs):
	from zatgo_core.chat_ai.erpnext.orchestrator import run_turn

	result = run_turn(**kwargs)
	try:
		import frappe
		from zatgo_core.chat_ai.core.events import EventPublisher

		session = kwargs.get("session_name") or ""
		pub = EventPublisher(session, enabled=True)
		pub.done("background_turn_complete")
		frappe.publish_realtime(
			"chat_ai:notify",
			{"title": "Chat AI", "message": "Background analysis complete"},
			user=frappe.session.user,
		)
	except Exception:
		pass
	return result
