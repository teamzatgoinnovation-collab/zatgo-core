"""Tool router — category gate, confirmation, execute via ToolPipeline."""

from __future__ import annotations

import time
from typing import Any, Callable

from zatgo_core.chat_ai.core.agent_limits import AgentLimits
from zatgo_core.chat_ai.core.tool_pipeline import ToolPipeline
from zatgo_core.chat_ai.core.tool_router.spec import (
	CATEGORY_READ,
	ConfirmationPolicy,
	ToolResult,
	ToolSpec,
)


class ToolRouter:
	def __init__(
		self,
		tools: list[ToolSpec],
		*,
		policy: ConfirmationPolicy | None = None,
		limits: AgentLimits | None = None,
		progress: Callable[[str, str], None] | None = None,
		session: str | None = None,
		timeout_seconds: int = 60,
		max_retries: int = 0,
		publisher=None,
		permission_engine=None,
	):
		self.tools = {t.name: t for t in tools}
		self.policy = policy or ConfirmationPolicy()
		self.limits = limits or AgentLimits()
		self.progress = progress or (lambda stage, detail="": None)
		self.session = session
		self.publisher = publisher
		self.permission_engine = permission_engine
		self._pipeline = ToolPipeline(
			self.tools,
			policy=self.policy,
			limits=self.limits,
			progress=self.progress,
			session=session,
			timeout_seconds=timeout_seconds,
			max_retries=max_retries,
			publisher=publisher,
			permission_engine=permission_engine,
		)
		self._calls = 0

	def list_openai_tools(self) -> list[dict]:
		out = []
		for t in self.tools.values():
			if not self.policy.category_allowed(t.category):
				continue
			out.append(t.to_openai_tool())
			if len(out) >= self.limits.max_tools_per_request:
				break
		return out

	def get(self, name: str) -> ToolSpec | None:
		return self.tools.get(name)

	def run(
		self,
		name: str,
		args: dict | None = None,
		*,
		confirmed: bool = False,
		risk_level: str = "medium",
	) -> ToolResult:
		result = self._pipeline.run(
			name,
			args,
			confirmed=confirmed,
			risk_level=risk_level,
			category_allowed_fn=lambda tool: self.policy.category_allowed(tool.category),
			needs_confirmation_fn=lambda tool, a, rl: self.policy.needs_confirmation(
				tool, a, risk_level=rl
			),
			progress_stage_fn=_progress_stage,
			invoke_fn=lambda tool, a: _invoke(tool.handler, a),
		)
		self._calls = self._pipeline._calls
		return result


def _ms(start: float) -> int:
	return int((time.time() - start) * 1000)


def _invoke(fn: Callable, args: dict):
	try:
		import inspect

		sig = inspect.signature(fn)
		params = sig.parameters
		if not params:
			return fn()
		if any(p.kind == p.VAR_KEYWORD for p in params.values()):
			return fn(**args)
		kwargs = {k: v for k, v in args.items() if k in params}
		# positional-only single "args" bag
		if len(params) == 1:
			name = next(iter(params))
			p = params[name]
			if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and name not in args:
				return fn(args)
		return fn(**kwargs)
	except TypeError:
		try:
			return fn(**args)
		except TypeError:
			return fn(args)
	except Exception:
		return fn(**args)


def _confirmation_message(tool: ToolSpec, args: dict) -> str:
	doctype = args.get("doctype") or (tool.supported_doctypes[0] if tool.supported_doctypes else "document")
	name = args.get("name") or args.get("title") or ""
	target = f"{doctype} {name}".strip()
	return f"This action will run `{tool.name}` on {target or 'the selected document'}. Continue?"


def _progress_stage(tool: ToolSpec) -> str:
	n = tool.name.lower()
	if "search" in n:
		return "searching"
	if any(x in n for x in ("approve", "reject", "workflow")):
		return "running_workflow"
	if any(x in n for x in ("report", "summary", "analytics", "status_brief", "company_status")):
		return "generating_report"
	if tool.category == "write" and any(x in n for x in ("create", "insert")):
		return "creating_document"
	return "reading_erp"
