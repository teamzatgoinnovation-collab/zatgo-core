"""One LLM round with live token streaming to the browser.

Text deltas are published as they arrive (coalesced to avoid one realtime
message per token); tool calls are assembled by the provider and returned in
the final result. Cancellation is checked between flushes; a stream that dies
midway returns what the user already saw instead of discarding it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import frappe

from zatgo_core.chat_ai.core.providers.base import LLMResult
from zatgo_core.chat_ai.core.providers.errors import ProviderError
from zatgo_core.chat_ai.core.tool_pipeline import is_cancelled
from zatgo_core.chat_ai.erpnext.events.realtime_events import publish_stream

FLUSH_CHARS = 12
FLUSH_SECONDS = 0.05


@dataclass
class RoundResult:
	result: LLMResult
	streamed: bool = False  # text was already shown live (don't replay it)
	stopped: bool = False  # user pressed Stop
	interrupted: bool = False  # provider failed after partial output


def stream_round(provider, messages, *, tools=None, settings=None, session: str = "", **opts) -> RoundResult:
	settings = settings or {}
	if not settings.get("enable_streaming", 1) or not session:
		return RoundResult(provider.chat(messages, tools=tools or None, **opts))

	parts: list[str] = []
	pending = ""
	last_flush = time.monotonic()
	final: LLMResult | None = None
	events = provider.chat_events(messages, tools=tools or None, **opts)
	try:
		for ev in events:
			if ev.kind == "text" and ev.text:
				parts.append(ev.text)
				pending += ev.text
				now = time.monotonic()
				if len(pending) >= FLUSH_CHARS or now - last_flush >= FLUSH_SECONDS:
					publish_stream(session, pending)
					pending, last_flush = "", now
					if is_cancelled(session):
						return RoundResult(LLMResult(content="".join(parts)), streamed=True, stopped=True)
			elif ev.kind == "result":
				final = ev.result
	except ProviderError as exc:
		if not parts:
			raise
		frappe.log_error(title=f"chat_ai stream interrupted ({exc.code})", message=exc.detail or str(exc))
		if pending:
			publish_stream(session, pending)
		return RoundResult(LLMResult(content="".join(parts)), streamed=True, interrupted=True)
	finally:
		close = getattr(events, "close", None)
		if close:
			close()
	if pending:
		publish_stream(session, pending)
	if final is None:  # provider ended without a result event: use what streamed
		final = LLMResult(content="".join(parts))
	return RoundResult(final, streamed=bool(parts))
