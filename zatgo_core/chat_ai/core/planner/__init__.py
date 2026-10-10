"""Planner — produce structured plan from user intent + context."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from zatgo_core.chat_ai.core.providers.base import LLMMessage, LLMProvider, LLMResult


@dataclass
class Plan:
	intent: str = ""
	slots: dict[str, Any] = field(default_factory=dict)
	needs_clarification: bool = False
	clarification_question: str = ""
	candidate_skills: list[str] = field(default_factory=list)
	candidate_tools: list[str] = field(default_factory=list)
	is_simple_question: bool = False
	risk_level: str = "medium"  # low|medium|high
	assumptions: list[str] = field(default_factory=list)
	implementation_plan: list[str] = field(default_factory=list)
	needs_plan_approval: bool = False
	raw_content: str = ""
	tokens_in: int = 0
	tokens_out: int = 0
	model: str = ""


PLAN_SCHEMA_HINT = """
Respond with JSON only:
{
  "intent": "short intent label",
  "slots": {},
  "is_simple_question": false,
  "risk_level": "low",
  "assumptions": [],
  "implementation_plan": ["Step one — tool: search", "Step two — tool: create_task"],
  "needs_plan_approval": false,
  "needs_clarification": false,
  "clarification_question": "",
  "candidate_skills": ["core"],
  "candidate_tools": ["search", "create_task"]
}

Rules:
- is_simple_question=true for how-to, definitions, navigation help (no ERP data mutation).
- needs_plan_approval=true when the request will create/update/delete/submit multiple records or bulk operations.
- risk_level: low (single safe create/read), medium (single submit/SO/PO), high (delete/bulk/import/settings).
- Use intelligent_defaults, context, and memory entities when available; do not ask for values already resolved.
- Leave assumptions empty for routine defaults (Company, Currency, Fiscal Year, Warehouse, Branch). Never emit "Using Company/Currency/Fiscal Year" lines. Only list an assumption when a real choice was made that the user should know.
- Never invent ERPNext document names or IDs. If required slots are missing, set needs_clarification true.
- candidate_tools: optional shortlist of tool names likely needed (prefer narrow skill tools over generic CRUD).
- Prefer naming the tool in each implementation_plan step when known.
"""


def plan(
	provider: LLMProvider,
	*,
	user_message: str,
	system_prompt: str,
	context: dict | None = None,
	history: list[dict] | None = None,
	available_skills: list[str] | None = None,
	available_tool_names: list[str] | None = None,
) -> Plan:
	messages: list[LLMMessage] = [
		LLMMessage(role="system", content=system_prompt + "\n\n" + PLAN_SCHEMA_HINT),
	]
	if context:
		messages.append(
			LLMMessage(
				role="system",
				content="Context stack (JSON):\n" + json.dumps(context, default=str)[:8000],
			)
		)
	if available_skills:
		messages.append(
			LLMMessage(
				role="system",
				content="Available skills: " + ", ".join(available_skills),
			)
		)
	if available_tool_names:
		messages.append(
			LLMMessage(
				role="system",
				content="Known tool names (prefer these in candidate_tools): "
				+ ", ".join(available_tool_names[:80]),
			)
		)
	for h in history or []:
		messages.append(LLMMessage(role=h.get("role") or "user", content=h.get("content") or ""))
	messages.append(LLMMessage(role="user", content=user_message))

	use_json = provider.capabilities.json_output
	result: LLMResult = provider.chat(messages, response_format="json" if use_json else None)
	parsed = _parse_plan(result.content, available_skills or ["core"], context, available_tool_names)
	parsed.raw_content = result.content or ""
	parsed.tokens_in = result.tokens_in
	parsed.tokens_out = result.tokens_out
	parsed.model = result.model
	return parsed


def _parse_plan(
	content: str,
	skills: list[str],
	context: dict | None = None,
	available_tool_names: list[str] | None = None,
) -> Plan:
	data = {}
	text = (content or "").strip()
	try:
		data = json.loads(text)
	except json.JSONDecodeError:
		m = re.search(r"\{[\s\S]*\}", text)
		if m:
			try:
				data = json.loads(m.group(0))
			except json.JSONDecodeError:
				data = {}
	if not data:
		return Plan(
			intent="general",
			needs_clarification=False,
			candidate_skills=skills[:3] or ["core"],
			raw_content=text,
		)
	cands = data.get("candidate_skills") or ["core"]
	if isinstance(cands, str):
		cands = [cands]
	cands = [c for c in cands if c in skills] or (["core"] if "core" in skills else skills[:1])
	risk = str(data.get("risk_level") or "medium").lower()
	if risk not in ("low", "medium", "high"):
		risk = "medium"
	assumptions = data.get("assumptions") or []
	if isinstance(assumptions, str):
		assumptions = [assumptions]
	# Merge context assumptions if planner omitted them (skip routine defaults)
	from zatgo_core.chat_ai.erpnext.context.defaults import filter_user_visible_assumptions

	ctx_assumptions = filter_user_visible_assumptions((context or {}).get("assumptions") or [])
	for a in ctx_assumptions:
		if a and a not in assumptions:
			assumptions.append(a)
	assumptions = filter_user_visible_assumptions(assumptions)
	impl = data.get("implementation_plan") or []
	if isinstance(impl, str):
		impl = [impl]
	tool_cands = data.get("candidate_tools") or []
	if isinstance(tool_cands, str):
		tool_cands = [tool_cands]
	known = set(available_tool_names or [])
	if known:
		tool_cands = [t for t in tool_cands if t in known]
	else:
		tool_cands = [str(t) for t in tool_cands if t]
	return Plan(
		intent=str(data.get("intent") or "general"),
		slots=data.get("slots") or {},
		needs_clarification=bool(data.get("needs_clarification")),
		clarification_question=str(data.get("clarification_question") or ""),
		candidate_skills=cands,
		candidate_tools=tool_cands,
		is_simple_question=bool(data.get("is_simple_question")),
		risk_level=risk,
		assumptions=[str(a) for a in assumptions if a],
		implementation_plan=[str(s) for s in impl if s],
		needs_plan_approval=bool(data.get("needs_plan_approval")),
	)


def merge_context_assumptions(plan: Plan, context: dict | None) -> Plan:
	from zatgo_core.chat_ai.erpnext.context.defaults import filter_user_visible_assumptions

	ctx_assumptions = filter_user_visible_assumptions((context or {}).get("assumptions") or [])
	for a in ctx_assumptions:
		if a and a not in plan.assumptions:
			plan.assumptions.append(a)
	plan.assumptions = filter_user_visible_assumptions(plan.assumptions)
	return plan
