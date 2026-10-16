"""Main chat orchestration — Planner → Skill Router → Tool Router → Response Builder."""

from __future__ import annotations

import json
import time
from pathlib import Path

import frappe
from frappe.utils import now_datetime

from zatgo_core.chat_ai.core.agent_limits import AgentLimits
from zatgo_core.chat_ai.core.memory import ConversationMemory
from zatgo_core.chat_ai.core.planner import plan as run_planner
from zatgo_core.chat_ai.core.providers.base import LLMMessage
from zatgo_core.chat_ai.core.providers.errors import ProviderError
from zatgo_core.chat_ai.core.routing import allowed_models, pick_model
from zatgo_core.chat_ai.erpnext import attachments as attachments_svc
from zatgo_core.chat_ai.core.providers.registry import ProviderRegistry
from zatgo_core.chat_ai.core.response import (
	AssistantResponse,
	build_from_tool_results,
	clarification,
	confirmation,
	plan_approval,
)
from zatgo_core.chat_ai.core.skills import clear_skills, discover, list_skills
from zatgo_core.chat_ai.core.tool_router import ToolRouter
from zatgo_core.chat_ai.core.tool_router.spec import ConfirmationPolicy, ToolSpec
from zatgo_core.chat_ai.erpnext.confirmation_tokens import consume_token, issue_token
from zatgo_core.chat_ai.core.approval import is_plan_approval_text
from zatgo_core.chat_ai.erpnext.context import build_context_stack
from zatgo_core.chat_ai.core.assistant_mode import (
	is_company_status_intent,
	resolve_assistant_mode,
	status_candidate_skills,
)
from zatgo_core.chat_ai.core.tool_enrichment import enrich_tool_args
from zatgo_core.chat_ai.core.artifacts import ArtifactBuilder, persist_artifacts
from zatgo_core.chat_ai.core.tool_pipeline import clear_cancel
from zatgo_core.chat_ai.erpnext.context.defaults import filter_user_visible_assumptions, strip_using_preamble
from zatgo_core.chat_ai.erpnext.streaming import stream_round
from zatgo_core.chat_ai.erpnext.events.realtime_events import publish_progress, publish_stream, publish_typed_stream
from zatgo_core.chat_ai.erpnext.settings import get_settings_dict
from zatgo_core.chat_ai.plugin.loader import load_all as load_plugins
from zatgo_core.chat_ai.core.prompts.framework import PromptBundleRegistry
from zatgo_core.chat_ai.erpnext.permissions.engine import PermissionEngine
from zatgo_core.chat_ai.erpnext.jobs.turn_jobs import should_run_background, enqueue_turn


def _skills_root() -> str:
	return str(Path(__file__).resolve().parent / "skills")


def load_skills():
	clear_skills()
	return discover(
		[_skills_root()],
		doctype_exists=lambda d: bool(frappe.db.exists("DocType", d)),
		app_installed=lambda a: a in frappe.get_installed_apps(),
	)


_MODE_ADDENDA = {
	"Document Assistant": "document",
	"Analytics Assistant": "analytics",
	"Developer Assistant": "developer",
	"Admin Assistant": "admin",
}


def get_prompt_text(settings: dict, skill_prompts: list[str] | None = None) -> str:
	from zatgo_core.chat_ai.core.i18n import language_prompt

	version = settings.get("prompt_bundle_version") or "v4"
	base_dir = Path(__file__).resolve().parents[1] / "core" / "prompts" / version
	base = base_dir / "assistant.md"
	if not base.exists():
		base = Path(__file__).resolve().parents[1] / "core" / "prompts" / "v1" / "assistant.md"
	text = base.read_text() if base.exists() else "You are an ERPNext AI Assistant."
	mode = settings.get("_assistant_mode") or settings.get("default_assistant_mode") or "ERP Assistant"
	text += f"\n\nActive assistant mode: {mode}."
	# Mode-specific addenda (v3+)
	mode_key = _MODE_ADDENDA.get(mode)
	mode_text = ""
	if mode_key and version in ("v3", "v4"):
		mode_file = base_dir / "modes" / f"{mode_key}.md"
		if mode_file.exists():
			mode_text = mode_file.read_text()
			text += "\n\n" + mode_text
	if is_company_status_intent(settings.get("_user_message") or ""):
		text += (
			"\n\nFor company status / business overview questions, call `company_status_brief` first, "
			"then narrate like a human briefing: short spoken overview, what needs attention, "
			"Company assumption once, and a few plain-language next steps. Never invent AR/AP/stock figures."
		)
	lang = settings.get("_language") or settings.get("default_language") or "en"
	text += "\n\n" + language_prompt(lang)
	# Plugin prompt inheritance
	plugin_extra = PromptBundleRegistry.compose("", skill_prompts=skill_prompts)
	if plugin_extra.strip():
		text += "\n\n" + plugin_extra
	else:
		for p in skill_prompts or []:
			if p:
				text += "\n\n" + p
	return text


# Core helpers always kept when shortlisting tools
_CORE_HELPER_TOOLS = frozenset(
	{
		"file_search",
		"analyze_table",
		"calculator",
		"web_search",
		"fetch_url",
		"search",
		"erp_search",
		"global_search",
		"vector_search",
		"metadata_search",
		"list_documents",
		"get_document",
		"get_doctype_meta",
	}
)


def collect_tools(
	skill_names: list[str] | None = None,
	*,
	candidate_tools: list[str] | None = None,
	settings: dict | None = None,
) -> list[ToolSpec]:
	settings = settings or {}
	skills = list_skills()
	if not skills:
		load_skills()
		skills = list_skills()
	wanted = set(skill_names or [s.name for s in skills])
	# Always include core and the workspace tools (files / calculator / web)
	wanted.add("core")
	wanted.add("workspace")
	tools: list[ToolSpec] = []
	for s in skills:
		if s.name not in wanted:
			continue
		tools.extend(s.tools or [])
	if settings.get("enable_plugin_tools", 1):
		try:
			from zatgo_core.chat_ai.plugin.api import get_registered_tools

			tools.extend(get_registered_tools())
		except Exception:
			pass
	# External tool sources (REST / MCP / integrations)
	try:
		from zatgo_core.chat_ai.core.tool_sources import load_external_tools

		tools.extend(load_external_tools(settings))
	except Exception:
		pass
	# dedupe by name
	by_name = {t.name: t for t in tools}
	tools = list(by_name.values())
	# Prefer planner shortlist when present; always keep core helpers
	if candidate_tools:
		wanted_names = set(candidate_tools) | _CORE_HELPER_TOOLS
		shortlisted = [t for t in tools if t.name in wanted_names]
		if shortlisted:
			# Ensure at least one search helper survives thin shortlists
			names = {t.name for t in shortlisted}
			if not names & _CORE_HELPER_TOOLS:
				for t in tools:
					if t.name in _CORE_HELPER_TOOLS:
						shortlisted.append(t)
						break
			tools = shortlisted
	return tools


def run_turn(
	*,
	session_name: str,
	user_message: str,
	client_context: dict | None = None,
	command: str | None = None,
	confirmed: bool = False,
	pending_tool: str | None = None,
	pending_args: dict | None = None,
	plan_confirmed: bool = False,
	confirmation_token: str | None = None,
	execution_mode: str | None = None,
	attachments: list | None = None,
	model: str | None = None,
	web: bool | None = None,
	regenerate: bool = False,
) -> dict:
	settings = get_settings_dict()
	settings["_turn_start"] = time.time()
	settings["_skip_user_insert"] = bool(regenerate)
	# Reload plugins every turn (cold worker + discovery)
	try:
		load_plugins(settings)
	except Exception:
		pass

	# Ownership must be checked before any enqueue / mutation.
	session = frappe.get_doc("AI Chat Session", session_name)
	roles = frappe.get_roles()
	if session.user != frappe.session.user and "System Manager" not in roles and "Chat AI Manager" not in roles:
		frappe.throw("Not permitted", frappe.PermissionError)

	# Clients cannot force scheduled enqueue; only managers/system may opt into background.
	mode = (execution_mode or "immediate").lower()
	if mode == "scheduled" and "System Manager" not in roles and "Chat AI Manager" not in roles:
		execution_mode = "immediate"

	# Background enqueue (avoid re-enqueue when already in worker)
	if execution_mode != "_worker" and should_run_background(user_message, settings, execution_mode):
		enqueue_turn(
			session_name=session_name,
			user_message=user_message,
			client_context=client_context,
			command=command,
			confirmed=confirmed,
			pending_tool=pending_tool,
			pending_args=pending_args,
			plan_confirmed=plan_confirmed,
			confirmation_token=confirmation_token,
			execution_mode="_worker",
		)
		return {
			"session": session_name,
			"queued": True,
			"execution_mode": "background",
			"content": "Working on this in the background… I'll notify when ready.",
			"assistant_mode": resolve_assistant_mode(client_context, user_message),
		}

	clear_cancel(session_name)

	# Per-request context for workspace tools (session scope, collected references).
	frappe.flags.chat_ai_session = session_name
	frappe.flags.chat_ai_refs = []
	frappe.flags.chat_ai_user_message = user_message or ""
	if web is not None and not web:
		settings["enable_web_search"] = 0  # the user switched the web toggle off for this message
	settings["_web_requested"] = bool(web)

	from zatgo_core.chat_ai.core.i18n import normalize_language

	resolved_mode = resolve_assistant_mode(
		client_context,
		user_message,
		getattr(session, "assistant_mode", None),
	)
	settings["_assistant_mode"] = resolved_mode
	settings["_user_message"] = user_message or ""
	if session.assistant_mode != resolved_mode:
		session.assistant_mode = resolved_mode
	settings["_language"] = normalize_language(
		getattr(session, "language", None) or settings.get("default_language") or "en"
	)
	limits = AgentLimits.from_settings(settings)
	policy = ConfirmationPolicy.from_settings(settings)

	memory = _load_memory(session_name)
	context = build_context_stack(client_context, memory.entities)
	if settings.get("enable_conversation_memory", 1) and memory.entities:
		context = dict(context or {})
		context["entities"] = memory.entities
		context["memory_note"] = (
			"Use entities as established working memory; do not re-ask for these values."
		)
	load_skills()
	available = [s.name for s in list_skills()]

	msg = user_message
	if command:
		msg = f"/{command} {user_message}".strip()
		cmd_skill = {
			"task": "projects",
			"project": "projects",
			"customer": "crm",
			"invoice": "accounts",
			"stock": "inventory",
			"status": "analytics",
		}.get(command)
		candidate_override = [cmd_skill, "core"] if cmd_skill and cmd_skill in available else None
	else:
		candidate_override = None

	if is_company_status_intent(user_message) or (command or "").lstrip("/") == "status":
		candidate_override = status_candidate_skills(available)

	publish_progress(session_name, "planning")

	# --- Token-based tool confirmation resume ---
	# A confirmed tool runs ONLY from a server-issued confirmation token, with
	# the tool and arguments stored when the user was asked -- never from the
	# client's pending_tool / pending_args (that ran any tool, writes included,
	# with no confirmation at all).
	token_tool = None
	if confirmation_token and confirmed:
		stored = consume_token(session_name, confirmation_token, expected_kind="tool")
		if stored and stored.get("tool"):
			token_tool = stored["tool"]
			pending_tool = token_tool
			pending_args = stored.get("args") or {}
	if not token_tool:
		pending_tool = None
		pending_args = None

	# --- Token-based plan approval resume ---
	approved_plan = None
	approved_candidate_tools = None
	if confirmation_token and (plan_confirmed or is_plan_approval_text(user_message)):
		stored = consume_token(session_name, confirmation_token, expected_kind="plan")
		if stored:
			approved_plan = stored.get("plan") or []
			approved_candidate_tools = stored.get("candidate_tools")
			plan_confirmed = True
			msg = stored.get("original_message") or msg

	_router_kwargs = dict(
		policy=policy,
		limits=limits,
		progress=lambda s, d="": publish_progress(session_name, s, d),
		session=session_name,
		timeout_seconds=int(settings.get("tool_timeout_seconds") or 60),
		max_retries=int(settings.get("tool_max_retries") or settings.get("max_retries") or 0),
		permission_engine=PermissionEngine,
	)

	if confirmed and pending_tool:
		tools = collect_tools(available, settings=settings)
		router = ToolRouter(tools, **_router_kwargs)
		tool_spec = router.get(pending_tool)
		enriched = enrich_tool_args(tool_spec, pending_args or {}, context)
		result = router.run(
			pending_tool,
			enriched,
			confirmed=True,
			risk_level="medium",
		)
		_log_tool(session_name, pending_tool, enriched, result, tool_spec=tool_spec)
		resp = build_from_tool_results(
			[{"ok": result.ok, "tool": pending_tool, "data": result.data, "error": result.error}]
		)
		return _persist(session, memory, user_message, resp, settings, tokens=(0, 0))

	atts = attachments_svc.load_for_turn(attachments, session_name)
	images = [a for a in atts if a["kind"] == "image"]
	manual_model = (model or "").strip()
	if manual_model and manual_model not in allowed_models(settings):
		frappe.throw("That model is not available.", frappe.ValidationError)
	routed, slot = (None, "manual") if manual_model else pick_model(
		settings, user_message or "", has_images=bool(images)
	)
	chosen = manual_model or routed
	if chosen:
		settings["default_model"] = chosen
	settings["_model_manual"] = bool(manual_model)
	settings["_route_slot"] = slot
	provider = ProviderRegistry.get_active(settings)
	if images and not (provider.capabilities.vision and settings.get("enable_vision", 1)):
		resp = AssistantResponse(
			markdown="The selected model can't read images. Choose a vision-capable model or remove the image."
		)
		return _persist(session, memory, user_message, resp, settings, tokens=(0, 0), error=True)
	if settings.get("_web_requested") and settings.get("enable_web_search") and not settings.get("web_search_api_key"):
		resp = AssistantResponse(
			markdown="Web search is turned on but no search API key is configured. Ask an administrator to set it in Chat AI Settings."
		)
		return _persist(session, memory, user_message, resp, settings, tokens=(0, 0), error=True)
	settings["_attachments"] = atts
	attachment_ctx = attachments_svc.prompt_context(atts)
	session_files = frappe.get_all(
		"AI Attachment", filters={"session": session_name, "status": "Ready"}, fields=["name", "file_name", "kind", "status", "chunk_count"], limit_page_length=25,
	)
	settings["_has_files"] = bool(session_files)
	earlier = [f for f in session_files if f["name"] not in {a["name"] for a in atts}]
	if earlier:
		attachment_ctx = (attachment_ctx + "\n\n" if attachment_ctx else "") + (
			"Earlier files in this conversation (use file_search / analyze_table):\n" + attachments_svc.manifest(earlier)
		)
	neg = ProviderRegistry.requires(provider, "chat")
	if not neg.ok:
		resp = AssistantResponse(markdown="Configured LLM provider cannot chat. Check Chat AI Settings.")
		return _persist(session, memory, user_message, resp, settings, tokens=(0, 0), error=True)

	skill_prompts = []
	history = memory.window(int(settings.get("max_history_length") or 40))
	# Tool names for planner shortlist (skills only; external tools added after plan)
	probe_tools = collect_tools(available, settings={**settings, "enable_rest_tools": 0, "enable_mcp_tools": 0, "enable_integrations": 0})
	plan_provider = provider
	if settings.get("enable_model_routing") and (settings.get("model_fast") or "").strip() and not manual_model:
		try:  # classification doesn't need the big model
			plan_provider = ProviderRegistry.get_active({**settings, "default_model": settings["model_fast"].strip()})
		except Exception:
			plan_provider = provider
	plan = run_planner(
		plan_provider,
		user_message=msg,
		system_prompt=get_prompt_text(settings),
		context=context,
		history=history,
		available_skills=available,
		available_tool_names=[t.name for t in probe_tools],
	)

	if is_company_status_intent(user_message):
		plan.is_simple_question = False
		if "company_status_brief" not in (plan.candidate_tools or []):
			plan.candidate_tools = list(plan.candidate_tools or []) + ["company_status_brief", "dashboard_summary"]
		plan.candidate_skills = status_candidate_skills(available)

	if plan.needs_clarification:
		resp = clarification(plan.clarification_question or "Could you provide more details?")
		return _persist(session, memory, user_message, resp, settings, tokens=(plan.tokens_in, plan.tokens_out), model=plan.model)

	# Simple question — direct answer without tools (not when files need searching)
	if plan.is_simple_question and not plan.needs_plan_approval and "[Approved plan]" not in msg and not (
		settings.get("_has_files") and "too large to include" in attachment_ctx
	):
		settings["_stream_session"] = session_name
		resp, answer = _direct_answer(
			provider, settings, msg + (("\n\n" + attachment_ctx) if attachment_ctx else ""), context, history, plan,
			images=attachments_svc.image_data_urls(atts),
		)
		return _persist(
			session, memory, user_message, resp, settings,
			tokens=(plan.tokens_in + answer.tokens_in, plan.tokens_out + answer.tokens_out),
			model=answer.model or plan.model, error=bool(resp.meta.get("interrupted")),
		)

	# Plan approval gate (unless already approved via token)
	if plan.needs_plan_approval and not plan_confirmed and not approved_plan:
		token = issue_token(
			session_name,
			{
				"kind": "plan",
				"plan": plan.implementation_plan,
				"assumptions": plan.assumptions,
				"original_message": msg,
				"candidate_skills": plan.candidate_skills,
				"candidate_tools": plan.candidate_tools,
				"risk_level": plan.risk_level,
			},
		)
		resp = plan_approval(
			"I'll proceed with this plan after you confirm:",
			plan.implementation_plan,
			filter_user_visible_assumptions(plan.assumptions),
			token=token,
		)
		return _persist(session, memory, user_message, resp, settings, tokens=(plan.tokens_in, plan.tokens_out), model=plan.model)

	candidates = candidate_override or plan.candidate_skills or ["core"]
	tool_shortlist = approved_candidate_tools or plan.candidate_tools or None
	if is_company_status_intent(user_message):
		tool_shortlist = list(set(tool_shortlist or []) | {"company_status_brief", "dashboard_summary"})
	if approved_plan:
		msg = msg + "\n\n[Approved plan]\n" + "\n".join(f"- {s}" for s in approved_plan)
	skills = [s for s in list_skills() if s.name in candidates]
	for s in skills:
		if s.prompt:
			skill_prompts.append(s.prompt)

	publish_progress(session_name, "routing")
	tools = _filter_workspace_tools(
		collect_tools(candidates, candidate_tools=tool_shortlist, settings=settings), settings
	)
	router = ToolRouter(tools, **_router_kwargs)
	risk_level = plan.risk_level or "medium"

	if not settings.get("enable_tool_calling", 1) or not provider.capabilities.tool_calling:
		if "search" in router.tools:
			args = enrich_tool_args(router.get("search"), {"query": user_message}, context)
			sr = router.run("search", args, confirmed=True, risk_level=risk_level)
			_log_tool(session_name, "search", args, sr, tool_spec=router.get("search"))
			resp = build_from_tool_results([{"ok": sr.ok, "tool": "search", "data": sr.data, "error": sr.error}])
		else:
			resp = AssistantResponse(markdown=plan.raw_content or f"Intent: {plan.intent}")
		return _persist(session, memory, user_message, resp, settings, tokens=(plan.tokens_in, plan.tokens_out), model=plan.model)

	openai_tools = router.list_openai_tools()
	visible_assumptions = filter_user_visible_assumptions(plan.assumptions)
	assumption_note = ""
	if visible_assumptions:
		assumption_note = "Assumptions:\n" + "\n".join(f"- {a}" for a in visible_assumptions[:5])
	memory_note = ""
	if settings.get("enable_conversation_memory", 1) and memory.entities:
		memory_note = "\n\nWorking memory entities:\n" + json.dumps(memory.entities, default=str)[:2000]
	messages = [
		LLMMessage(role="system", content=get_prompt_text(settings, skill_prompts)),
		LLMMessage(
			role="system",
			content="Context:\n" + json.dumps(context, default=str)[:6000]
			+ (("\n\n" + assumption_note) if assumption_note else "")
			+ memory_note,
		),
	]
	for h in _history_for_llm(history, 10):
		messages.append(LLMMessage(role=h["role"], content=h["content"]))
	web_hint = (
		"\n\n(The user asked you to use web search for this message.)"
		if settings.get("_web_requested") and settings.get("enable_web_search")
		else ""
	)
	messages.append(
		LLMMessage(
			role="user",
			content=msg + (("\n\n" + attachment_ctx) if attachment_ctx else "") + web_hint,
			images=attachments_svc.image_data_urls(atts) or None,
		)
	)

	tool_results = []
	total_in, total_out = plan.tokens_in, plan.tokens_out
	rounds = 0
	while rounds < limits.max_tool_rounds:
		rounds += 1
		try:
			rnd = stream_round(
				provider, messages, tools=openai_tools or None, settings=settings, session=session_name
			)
		except ProviderError as exc:
			fallback = _fallback_provider(settings, exc)
			if fallback is None:
				raise
			provider = fallback
			rnd = stream_round(
				provider, messages, tools=openai_tools or None, settings=settings, session=session_name
			)
		result = rnd.result
		total_in += result.tokens_in
		total_out += result.tokens_out

		if rnd.stopped or rnd.interrupted:
			note = "\n\n_(stopped)_" if rnd.stopped else "\n\n_(the connection to the AI provider was interrupted)_"
			resp = AssistantResponse(markdown=strip_using_preamble(result.content or "").strip() + note)
			publish_progress(session_name, "done")
			publish_stream(session_name, "", done=True)
			return _persist(
				session, memory, user_message, resp, settings, tokens=(total_in, total_out),
				model=result.model, tool_results=tool_results, error=rnd.interrupted,
			)

		if not result.tool_calls:
			if rnd.streamed:
				md = result.content or "Done."
			else:
				md = _stream_final_answer(
					provider,
					messages,
					settings,
					session_name,
					fallback=result.content or "Done.",
					assumptions=plan.assumptions,
					already_content=result.content,
				)
			md = strip_using_preamble(md)
			# Do not prepend Using Company/Currency/FY lines to chat replies
			resp = AssistantResponse(markdown=md)
			# Attach blocks from prior tool results if any
			if tool_results:
				built = build_from_tool_results(tool_results)
				resp.blocks = built.blocks
			publish_progress(session_name, "done")
			publish_stream(session_name, "", done=True)
			return _persist(
				session,
				memory,
				user_message,
				resp,
				settings,
				tokens=(total_in, total_out),
				model=result.model,
				tool_results=tool_results,
			)

		if rnd.streamed and result.content:
			# The model narrated before calling tools; the final answer starts fresh.
			publish_stream(session_name, "", reset=True)
		messages.append(
			LLMMessage(role="assistant", content=result.content or "", tool_calls=result.tool_calls)
		)
		for tc in result.tool_calls:
			fn = (tc.get("function") or {})
			name = fn.get("name") or tc.get("name")
			raw_args = fn.get("arguments") or "{}"
			try:
				args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
			except json.JSONDecodeError:
				args = {}
			tool_spec = router.get(name)
			args = enrich_tool_args(tool_spec, args, context)
			tr = router.run(name, args, confirmed=False, risk_level=risk_level)
			_log_tool(session_name, name, args, tr, tool_spec=tool_spec)
			if tr.needs_confirmation:
				token = issue_token(
					session_name,
					{"kind": "tool", "tool": name, "args": args},
				)
				resp = confirmation(tr.confirmation_message, name, args, token=token)
				publish_progress(session_name, "done")
				return _persist(session, memory, user_message, resp, settings, tokens=(total_in, total_out), model=result.model)
			tool_results.append({"ok": tr.ok, "tool": name, "data": tr.data, "error": tr.error})
			if tr.ok:
				memory.update_entities_from_tool(name, tr.data)
			messages.append(
				LLMMessage(
					role="tool",
					content=json.dumps({"ok": tr.ok, "data": tr.data, "error": tr.error}, default=str)[:8000],
					tool_call_id=tc.get("id"),
					name=name,
				)
			)

	resp = build_from_tool_results(tool_results, preface="Here’s what I found:")
	resp.markdown = strip_using_preamble(resp.markdown)
	publish_progress(session_name, "done")
	if settings.get("enable_streaming", 1):
		publish_typed_stream(session_name, resp.markdown or "", chunk_size=5)
	else:
		publish_stream(session_name, resp.markdown or "", done=True)
	return _persist(
		session,
		memory,
		user_message,
		resp,
		settings,
		tokens=(total_in, total_out),
		tool_results=tool_results,
	)


def _stream_final_answer(
	provider,
	messages,
	settings,
	session_name,
	*,
	fallback: str,
	assumptions=None,
	already_content: str | None = None,
) -> str:
	"""Stream final assistant text when enabled; otherwise return fallback content.

	Always strip leading 'Using …' preambles before typing/stream publish so Desk
	never shows Company/Currency/FY boilerplate.
	"""
	# When the non-stream chat already returned content without tool_calls, publish it
	# in typing-sized chunks for Desk UX.
	if already_content:
		cleaned = strip_using_preamble(already_content)
		if settings.get("enable_streaming", 1):
			publish_typed_stream(session_name, cleaned, chunk_size=5)
		return cleaned
	if not settings.get("enable_streaming", 1):
		return strip_using_preamble(fallback)
	parts: list[str] = []
	try:
		for chunk in provider.chat_stream(messages):
			if not chunk:
				continue
			parts.append(chunk)
	except Exception:
		return strip_using_preamble(fallback)
	cleaned = strip_using_preamble("".join(parts) or fallback)
	publish_typed_stream(session_name, cleaned, chunk_size=5)
	return cleaned


def _history_for_llm(history: list | None, limit: int = 6) -> list:
	"""Pass recent turns to the model with assistant 'Using …' noise stripped."""
	out = []
	for h in (history or [])[-limit:]:
		role = h.get("role") if isinstance(h, dict) else None
		content = (h.get("content") if isinstance(h, dict) else None) or ""
		if role == "assistant":
			content = strip_using_preamble(content)
		out.append({"role": role, "content": content})
	return out


def _direct_answer(provider, settings, msg, context, history, plan, images=None):
	"""Answer simple how-to / explanation questions without tool calls."""
	messages = [
		LLMMessage(role="system", content=get_prompt_text(settings)),
		LLMMessage(
			role="system",
			content=(
				"Context:\n"
				+ json.dumps(context, default=str)[:4000]
				+ "\n\nNever start replies with 'Using Company/Currency/Fiscal Year' lines."
			),
		),
	]
	for h in _history_for_llm(history, 6):
		messages.append(LLMMessage(role=h["role"], content=h["content"]))
	messages.append(
		LLMMessage(
			role="user",
			content=msg
			+ "\n\n(Answer like a helpful coworker: natural, short, and clear. "
			"No tools. No long documentation. No 'Using …' preamble.)",
			images=images or None,
		)
	)
	session_name = settings.get("_stream_session") or ""
	try:
		rnd = stream_round(provider, messages, settings=settings, session=session_name)
	except ProviderError as exc:
		fallback = _fallback_provider(settings, exc)
		if fallback is None:
			raise
		rnd = stream_round(fallback, messages, settings=settings, session=session_name)
	md = strip_using_preamble(rnd.result.content or plan.raw_content or "Done.")
	meta = {}
	if rnd.stopped:
		md += "\n\n_(stopped)_"
	elif rnd.interrupted:
		md += "\n\n_(the connection to the AI provider was interrupted)_"
		meta["interrupted"] = True
	if session_name:
		if settings.get("enable_streaming", 1) and not rnd.streamed:
			publish_typed_stream(session_name, md, chunk_size=5)  # provider could not stream
		else:
			publish_stream(session_name, "", done=True)
	return AssistantResponse(markdown=md, meta=meta), rnd.result


def _load_memory(session_name: str) -> ConversationMemory:
	mem = ConversationMemory()
	msgs = frappe.get_all(
		"AI Chat Message",
		filters={"session": session_name},
		fields=["role", "content"],
		order_by="creation asc",
		limit_page_length=100,
	)
	for m in msgs:
		mem.add(m.role, m.content or "")
	row = frappe.db.get_value("AI Chat Memory", {"session": session_name}, ["name", "entities_json"], as_dict=True)
	if row and row.entities_json:
		try:
			mem.entities = json.loads(row.entities_json)
		except Exception:
			pass
	return mem


def _persist(session, memory, user_message, resp: AssistantResponse, settings, tokens=(0, 0), model="", error=False, tool_results=None):
	start = time.time()
	resp.markdown = strip_using_preamble(resp.markdown)
	turn_start = settings.get("_turn_start") or start
	refs = list(getattr(frappe.flags, "chat_ai_refs", None) or [])
	if refs and not resp.sources:
		resp.sources = refs[:20]
	resp.meta = {
		**(resp.meta or {}),
		"model": model or settings.get("default_model"),
		"route": settings.get("_route_slot"),
		**({"fallback_from": settings["_fallback_from"]} if settings.get("_fallback_from") else {}),
	}
	atts = settings.get("_attachments") or []
	# user message (a regenerate keeps the existing one)
	if not settings.get("_skip_user_insert"):
		frappe.get_doc(
			{
				"doctype": "AI Chat Message",
				"session": session.name,
				"role": "user",
				"content": user_message,
				"attachments": frappe.as_json(
					[{"name": a["name"], "file_name": a["file_name"], "kind": a["kind"]} for a in atts]
				) if atts else "",
			}
		).insert(ignore_permissions=True)

	# Enrich blocks from company status / tool results
	if tool_results:
		try:
			from zatgo_core.chat_ai.core.response import ContentBlock

			arts = ArtifactBuilder.from_tool_results(tool_results)
			for art in arts:
				if art.artifact_type == "table" and art.content:
					resp.blocks.append(ContentBlock(type="table", data=art.content))
				elif art.artifact_type in ("report", "markdown") and isinstance(art.content, dict):
					md = art.content.get("markdown") or ""
					if md and md not in (resp.markdown or ""):
						resp.markdown = (md + "\n\n" + (resp.markdown or "")).strip()
				elif art.artifact_type == "checklist":
					resp.blocks.append(
						ContentBlock(type="plan", data={"steps": (art.content or {}).get("items") or []})
					)
				elif art.artifact_type == "chart" and art.content:
					resp.blocks.append(ContentBlock(type="chart", data=art.content))
		except Exception:
			pass

	cost = _cost(settings, tokens[0], tokens[1])
	assistant = frappe.get_doc(
		{
			"doctype": "AI Chat Message",
			"session": session.name,
			"role": "assistant",
			"content": resp.markdown,
			"content_json": frappe.as_json(resp.to_content_json()),
			"model": model,
			"provider": settings.get("provider"),
			"prompt_version": settings.get("prompt_bundle_version") or "v4",
			"tokens_in": tokens[0],
			"tokens_out": tokens[1],
			"latency_ms": int((time.time() - turn_start) * 1000),
			"cost_estimate": cost,
			"error": "1" if error else "",
		}
	)
	assistant.insert(ignore_permissions=True)

	artifact_ids = []
	try:
		from zatgo_core.chat_ai.core.events import EventPublisher

		pub = EventPublisher(session.name, enabled=bool(settings.get("enable_event_stream", 1)))
		arts = []
		if tool_results:
			arts.extend(ArtifactBuilder.from_tool_results(tool_results))
		arts.extend(ArtifactBuilder.from_content_blocks(resp.blocks))
		artifact_ids = persist_artifacts(
			session=session.name,
			message=assistant.name,
			artifacts=arts,
			publisher=pub,
		)
	except Exception:
		frappe.log_error(title="chat_ai artifact persist")

	session.last_message_at = now_datetime()
	if not session.title or session.title == "New chat":
		session.title = (user_message or "Chat")[:60]
	session.save(ignore_permissions=True)

	_save_memory(session.name, memory)
	_record_usage(settings, tokens, cost, error=error, latency=assistant.latency_ms)

	return {
		"session": session.name,
		"message": assistant.name,
		"content": resp.markdown,
		"content_json": resp.to_content_json(),
		"assistant_mode": settings.get("_assistant_mode") or session.assistant_mode or "ERP Assistant",
		"artifacts": artifact_ids,
		"needs_confirmation": resp.needs_confirmation,
		"confirmation_message": resp.confirmation_message,
		"pending_tool": resp.pending_tool,
		"pending_args": resp.pending_args,
		"needs_plan_approval": resp.needs_plan_approval,
		"pending_plan": resp.pending_plan,
		"pending_assumptions": resp.pending_assumptions,
		"confirmation_token": resp.confirmation_token,
		"sources": resp.sources,
		"meta": resp.meta,
	}


def _fallback_provider(settings: dict, exc: ProviderError):
	"""Provider for the configured fallback model, or None.

	Only for failures a different model can fix, never when the user picked the
	model themselves (they get the error and a retry), and the switch is recorded
	so the UI can say so."""
	if settings.get("_model_manual") or exc.code in ("auth", "bad_request", "not_configured"):
		return None
	fb = (settings.get("fallback_model") or "").strip()
	if not fb or fb == settings.get("default_model"):
		return None
	try:
		provider = ProviderRegistry.get_active({**settings, "default_model": fb})
	except Exception:
		return None
	settings["_fallback_from"] = settings.get("default_model")
	settings["default_model"] = fb
	frappe.log_error(title=f"chat_ai fallback to {fb} ({exc.code})", message=exc.detail or str(exc))
	return provider


def _filter_workspace_tools(tools: list, settings: dict) -> list:
	"""Offer workspace tools only where they can work: web tools need the switch and a
	key, file tools need files in the conversation."""
	web_ok = bool(settings.get("enable_web_search") and settings.get("web_search_api_key"))
	files_ok = bool(settings.get("_has_files"))
	hide = set()
	if not web_ok:
		hide |= {"web_search", "fetch_url"}
	if not files_ok:
		hide |= {"file_search", "analyze_table"}
	return [t for t in tools if t.name not in hide]


def _save_memory(session_name: str, memory: ConversationMemory):
	existing = frappe.db.get_value("AI Chat Memory", {"session": session_name}, "name")
	payload = {
		"entities_json": frappe.as_json(memory.entities),
		"user": frappe.session.user,
		"session": session_name,
	}
	if existing:
		doc = frappe.get_doc("AI Chat Memory", existing)
		doc.update(payload)
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({"doctype": "AI Chat Memory", **payload}).insert(ignore_permissions=True)


def _log_tool(session_name, name, args, result, tool_spec=None):
	try:
		if not frappe.db.get_single_value("Chat AI Settings", "enable_audit_logs"):
			return
		# Never persist secrets
		safe_args = _redact_args(args or {})
		source = "python"
		category = ""
		if tool_spec is not None:
			source = getattr(tool_spec, "source", None) or "python"
			category = getattr(tool_spec, "category", None) or ""
		frappe.get_doc(
			{
				"doctype": "AI Tool Log",
				"session": session_name,
				"user": frappe.session.user,
				"tool_name": name,
				"source": source,
				"category": category,
				"args_json": frappe.as_json(safe_args),
				"result_json": frappe.as_json({"data": result.data, "error": result.error}),
				"permission_ok": 1 if result.permission_ok else 0,
				"success": 1 if result.ok else 0,
				"error": result.error,
				"latency_ms": result.latency_ms,
			}
		).insert(ignore_permissions=True)
	except Exception:
		pass


def _redact_args(args: dict) -> dict:
	sensitive = {"api_key", "api_token", "auth_token", "password", "secret", "token", "authorization"}
	out = {}
	for k, v in (args or {}).items():
		if str(k).lower() in sensitive or "token" in str(k).lower() or "secret" in str(k).lower():
			out[k] = "***"
		else:
			out[k] = v
	return out


def _cost(settings, tin, tout) -> float:
	pi = float(settings.get("token_price_input") or 0)
	po = float(settings.get("token_price_output") or 0)
	return (tin / 1_000_000.0) * pi + (tout / 1_000_000.0) * po


def _record_usage(settings, tokens, cost, error=False, latency=0):
	"""Per-user/day/model counters. Increments happen in SQL so concurrent
	turns cannot overwrite each other's counts; the insert races are resolved
	by the unique lookup below plus a retry."""
	try:
		from frappe.utils import today

		user = frappe.session.user
		provider = settings.get("provider")
		model = settings.get("default_model")
		key = {"usage_date": today(), "user": user, "provider": provider, "model": model}
		for _attempt in range(2):
			existing = frappe.db.get_value("AI Usage Daily", key, "name")
			if not existing:
				frappe.db.savepoint("chat_ai_usage")
				try:
					frappe.get_doc(
						{
							"doctype": "AI Usage Daily",
							**key,
							"tokens_in": 0,
							"tokens_out": 0,
							"cost_estimate": 0,
							"request_count": 0,
							"error_count": 0,
							"avg_latency_ms": 0,
						}
					).insert(ignore_permissions=True)
				except Exception:
					frappe.db.rollback(save_point="chat_ai_usage")
				existing = frappe.db.get_value("AI Usage Daily", key, "name")
			if existing:
				frappe.db.sql(
					"""update `tabAI Usage Daily` set
						tokens_in = coalesce(tokens_in, 0) + %s,
						tokens_out = coalesce(tokens_out, 0) + %s,
						cost_estimate = coalesce(cost_estimate, 0) + %s,
						avg_latency_ms = (coalesce(avg_latency_ms, 0) * coalesce(request_count, 0) + %s)
							/ (coalesce(request_count, 0) + 1),
						request_count = coalesce(request_count, 0) + 1,
						error_count = coalesce(error_count, 0) + %s
						where name = %s""",
					(tokens[0], tokens[1], cost, latency or 0, 1 if error else 0, existing),
				)
				return
	except Exception:
		frappe.log_error(title="chat_ai._record_usage")
