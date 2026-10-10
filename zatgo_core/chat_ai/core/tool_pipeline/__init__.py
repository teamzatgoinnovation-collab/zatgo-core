"""Tool execution pipeline stages behind ToolRouter."""

from __future__ import annotations

import time
from typing import Any, Callable

from zatgo_core.chat_ai.core.tool_router.spec import ToolResult, ToolSpec


def cancel_key(session: str) -> str:
	return f"chat_ai:cancel:{session}"


def is_cancelled(session: str | None) -> bool:
	if not session:
		return False
	try:
		import frappe

		return bool(frappe.cache.get_value(cancel_key(session)))
	except Exception:
		return False


def clear_cancel(session: str | None):
	if not session:
		return
	try:
		import frappe

		frappe.cache.delete_value(cancel_key(session))
	except Exception:
		pass


def request_cancel(session: str):
	try:
		import frappe

		frappe.cache.set_value(cancel_key(session), 1, expires_in_sec=300)
	except Exception:
		pass


class ToolPipeline:
	"""Resolver → PermissionEngine → Executor → Retry → Formatter → ArtifactBuilder."""

	def __init__(
		self,
		tools: dict[str, ToolSpec],
		*,
		policy=None,
		limits=None,
		progress: Callable[[str, str], None] | None = None,
		session: str | None = None,
		timeout_seconds: int = 60,
		max_retries: int = 0,
		publisher=None,
		permission_engine=None,
	):
		self.tools = tools
		self.policy = policy
		self.limits = limits
		self.progress = progress or (lambda stage, detail="": None)
		self.session = session
		self.timeout_seconds = int(timeout_seconds or 60)
		self.max_retries = int(max_retries or 0)
		self.publisher = publisher
		self.permission_engine = permission_engine
		self._calls = 0

	def resolve(self, name: str) -> ToolSpec | None:
		return self.tools.get(name)

	def run(
		self,
		name: str,
		args: dict | None = None,
		*,
		confirmed: bool = False,
		risk_level: str = "medium",
		invoke_fn: Callable | None = None,
		needs_confirmation_fn: Callable | None = None,
		category_allowed_fn: Callable | None = None,
		progress_stage_fn: Callable | None = None,
	) -> ToolResult:
		args = args or {}
		if is_cancelled(self.session):
			return ToolResult(ok=False, error="Cancelled by user")

		tool = self.resolve(name)
		if not tool:
			return ToolResult(ok=False, error=f"Unknown tool: {name}")

		if category_allowed_fn and not category_allowed_fn(tool):
			return ToolResult(
				ok=False,
				error=f"Tool category '{tool.category}' is not allowed",
				permission_ok=False,
			)

		# Permission engine (narrowing)
		if self.permission_engine is not None:
			try:
				decision = self.permission_engine.evaluate(tool, args, context={})
				if not decision.allowed:
					return ToolResult(ok=False, error=decision.reason or "Permission denied", permission_ok=False)
			except Exception as exc:
				return ToolResult(ok=False, error=str(exc), permission_ok=False)

		limits = self.limits
		if limits is not None and self._calls >= getattr(limits, "max_tool_calls", 999):
			return ToolResult(ok=False, error="Max tool calls exceeded")

		if needs_confirmation_fn and needs_confirmation_fn(tool, args, risk_level) and not confirmed:
			from zatgo_core.chat_ai.core.tool_router import _confirmation_message

			return ToolResult(
				ok=False,
				needs_confirmation=True,
				confirmation_message=_confirmation_message(tool, args),
				data=args,
			)

		stage = progress_stage_fn(tool) if progress_stage_fn else "reading_erp"
		self.progress(stage, tool.name)
		if self.publisher:
			self.publisher.tool_started(tool.name, stage)

		self._calls += 1
		attempts = max(1, self.max_retries + 1)
		last_err = None
		start = time.time()
		invoke = invoke_fn
		for attempt in range(attempts):
			if is_cancelled(self.session):
				return ToolResult(ok=False, error="Cancelled by user", latency_ms=_ms(start))
			try:
				if not tool.handler and not invoke:
					return ToolResult(ok=False, error="Tool has no handler", latency_ms=_ms(start))
				data = invoke(tool, args) if invoke else None
				if invoke is None:
					from zatgo_core.chat_ai.core.tool_router import _invoke

					data = _invoke(tool.handler, args)
				formatted = self._format(tool, data)
				if self.publisher:
					self.publisher.tool_finished(tool.name, True)
				return ToolResult(ok=True, data=formatted, latency_ms=_ms(start))
			except PermissionError as exc:
				return ToolResult(ok=False, error=str(exc), permission_ok=False, latency_ms=_ms(start))
			except Exception as exc:
				last_err = str(exc)
				if attempt + 1 < attempts:
					if self.publisher:
						self.publisher.tool_progress(tool.name, f"retry {attempt + 1}", stage)
					continue
				if self.publisher:
					self.publisher.tool_finished(tool.name, False, last_err)
				return ToolResult(ok=False, error=last_err, latency_ms=_ms(start))
		return ToolResult(ok=False, error=last_err or "Tool failed", latency_ms=_ms(start))

	def _format(self, tool: ToolSpec, data: Any) -> Any:
		# Passthrough; ArtifactBuilder consumes structured results later
		return data


def _ms(start: float) -> int:
	return int((time.time() - start) * 1000)
