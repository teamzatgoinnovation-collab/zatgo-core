"""Whitelisted chat API."""

from __future__ import annotations

import json

import frappe
from frappe import _

from zatgo_core.chat_ai.api.response import fail, ok
from zatgo_core.chat_ai.core.providers.errors import ProviderError
from zatgo_core.chat_ai.core.quota import QuotaExceeded, enforce as enforce_quota, enforce_upload
from zatgo_core.chat_ai.erpnext.orchestrator import run_turn
from zatgo_core.chat_ai.plugin.api import get_commands
from zatgo_core.chat_ai.plugin.loader import load_all


def _ensure_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Login required"), frappe.PermissionError)


@frappe.whitelist()
def send(
	session=None,
	message=None,
	client_context=None,
	command=None,
	confirmed=None,
	pending_tool=None,
	pending_args=None,
	plan_confirmed=None,
	confirmation_token=None,
	execution_mode=None,
	attachments=None,
	model=None,
	web=None,
	regenerate=None,
):
	_ensure_user()
	if isinstance(client_context, str):
		client_context = json.loads(client_context or "{}")
	if isinstance(pending_args, str):
		pending_args = json.loads(pending_args or "{}")
	if isinstance(attachments, str):
		attachments = json.loads(attachments or "[]")
	if not isinstance(attachments, list):
		attachments = []
	message = message or ""
	try:
		enforce_quota()
	except QuotaExceeded as exc:
		return fail(str(exc), code="rate_limited", retryable=True)
	if session:
		_assert_session_access(session)
	else:
		session = _create_session()
	try:
		data = run_turn(
			session_name=session,
			user_message=message,
			client_context=client_context or {},
			command=command,
			confirmed=frappe.utils.cint(confirmed),
			pending_tool=pending_tool,
			pending_args=pending_args or {},
			plan_confirmed=frappe.utils.cint(plan_confirmed),
			confirmation_token=confirmation_token,
			execution_mode=execution_mode,
			attachments=attachments,
			model=model or None,
			web=None if web is None else bool(frappe.utils.cint(web)),
			regenerate=bool(frappe.utils.cint(regenerate)),
		)
		return ok(data)
	except ProviderError as exc:
		frappe.log_error(title=f"chat_ai.send provider {exc.code}", message=exc.detail or str(exc))
		return fail(exc.message, code=exc.code, retryable=exc.retryable)
	except frappe.PermissionError:
		return fail(_("Not permitted"), code="forbidden")
	except frappe.ValidationError as exc:
		return fail(str(exc), code="invalid")
	except Exception:
		frappe.log_error(title="chat_ai.send")
		return fail(_("The assistant ran into a problem. Please try again."), code="internal", retryable=True)


@frappe.whitelist()
def cancel(session=None):
	_ensure_user()
	_assert_session_access(session)
	from zatgo_core.chat_ai.core.tool_pipeline import request_cancel

	request_cancel(session)
	return ok({"cancelled": True})


@frappe.whitelist()
def history(session=None, limit=50, before=None):
	"""Newest `limit` messages (oldest first). Pass `before` (a message's creation
	timestamp from a previous page) to load older ones."""
	_ensure_user()
	if not session:
		return fail("session required")
	_assert_session_access(session)
	limit = max(1, min(frappe.utils.cint(limit) or 50, 200))
	filters = {"session": session}
	if before:
		filters["creation"] = ("<", before)
	rows = frappe.get_all(
		"AI Chat Message",
		filters=filters,
		fields=[
			"name", "role", "content", "content_json", "creation", "tokens_in", "tokens_out",
			"model", "attachments", "error",
		],
		order_by="creation desc",
		limit_page_length=limit + 1,
	)
	has_more = len(rows) > limit
	rows = list(reversed(rows[:limit]))
	return ok(rows, has_more=has_more)


@frappe.whitelist()
def list_sessions(status="Active"):
	_ensure_user()
	filters = {"user": frappe.session.user}
	if status:
		filters["status"] = status
	rows = frappe.get_all(
		"AI Chat Session",
		filters=filters,
		fields=["name", "title", "assistant_mode", "status", "is_pinned", "last_message_at", "modified"],
		order_by="is_pinned desc, last_message_at desc, modified desc",
		limit_page_length=100,
	)
	return ok(rows)


@frappe.whitelist()
def clear(session=None):
	_ensure_user()
	_assert_session_access(session)
	for name in frappe.get_all("AI Chat Message", filters={"session": session}, pluck="name"):
		frappe.delete_doc("AI Chat Message", name, ignore_permissions=True, force=True)
	return ok({"cleared": True})


@frappe.whitelist()
def rename(session=None, title=None):
	_ensure_user()
	_assert_session_access(session)
	doc = frappe.get_doc("AI Chat Session", session)
	doc.title = title or doc.title
	doc.save(ignore_permissions=True)
	return ok({"name": doc.name, "title": doc.title})


@frappe.whitelist()
def set_mode(session=None, assistant_mode=None):
	_ensure_user()
	_assert_session_access(session)
	doc = frappe.get_doc("AI Chat Session", session)
	doc.assistant_mode = assistant_mode or doc.assistant_mode
	doc.save(ignore_permissions=True)
	return ok({"name": doc.name, "assistant_mode": doc.assistant_mode})


@frappe.whitelist()
def archive(session=None):
	_ensure_user()
	_assert_session_access(session)
	doc = frappe.get_doc("AI Chat Session", session)
	doc.status = "Archived"
	doc.save(ignore_permissions=True)
	return ok({"name": doc.name, "status": doc.status})


@frappe.whitelist()
def pin(session=None, pinned=1):
	_ensure_user()
	_assert_session_access(session)
	doc = frappe.get_doc("AI Chat Session", session)
	doc.is_pinned = frappe.utils.cint(pinned)
	doc.save(ignore_permissions=True)
	return ok({"name": doc.name, "is_pinned": doc.is_pinned})


@frappe.whitelist()
def delete_session(session=None):
	_ensure_user()
	_assert_session_access(session)
	from zatgo_core.chat_ai.erpnext.sessions import purge_session

	purge_session(session)
	return ok({"deleted": session})


@frappe.whitelist()
def search_sessions(query=None):
	"""Sessions matching by title or by message text, newest first. Each row says
	where it matched and carries a snippet for message matches."""
	_ensure_user()
	query = (query or "").strip()[:200]
	user = frappe.session.user
	fields = ["name", "title", "assistant_mode", "status", "is_pinned", "last_message_at"]
	if not query:
		return ok(frappe.get_all("AI Chat Session", filters={"user": user}, fields=fields, order_by="last_message_at desc", limit_page_length=50))
	rows = {
		r.name: {**r, "match": "title", "snippet": ""}
		for r in frappe.get_all(
			"AI Chat Session", filters={"user": user, "title": ("like", f"%{query}%")}, fields=fields, limit_page_length=50
		)
	}
	for hit in _message_hits(query, user, 50):
		if hit["session"] not in rows:
			meta = frappe.db.get_value("AI Chat Session", hit["session"], fields, as_dict=True)
			rows[hit["session"]] = {**meta, "match": "message", "snippet": hit["snippet"]}
	return ok(list(rows.values())[:50])


def _snippet(text: str, query: str, width: int = 140) -> str:
	text = text or ""
	i = text.lower().find(query.lower().split()[0]) if query.split() else -1
	start = max(0, i - width // 2) if i >= 0 else 0
	chunk = text[start : start + width].replace("\n", " ")
	return ("…" if start else "") + chunk + ("…" if start + width < len(text) else "")


def _message_hits(query: str, user: str, limit: int) -> list[dict]:
	"""Best message per session among the user's own conversations. FULLTEXT
	(natural-language mode, so user input can't inject operators) with a LIKE
	fallback for short terms or when the index is missing."""
	rows = []
	try:
		rows = frappe.db.sql(
			"""select m.session, m.content, m.creation from `tabAI Chat Message` m
			join `tabAI Chat Session` s on s.name = m.session
			where s.user = %(user)s and match(m.content) against (%(q)s in natural language mode)
			order by m.creation desc limit %(limit)s""",
			{"user": user, "q": query, "limit": limit * 3},
			as_dict=True,
		)
	except Exception:
		rows = []  # index missing / query unsupported
	if not rows:
		rows = frappe.db.sql(
			"""select m.session, m.content, m.creation from `tabAI Chat Message` m
			join `tabAI Chat Session` s on s.name = m.session
			where s.user = %(user)s and m.content like %(like)s
			order by m.creation desc limit %(limit)s""",
			{"user": user, "like": "%" + query.replace("%", "\\%").replace("_", "\\_") + "%", "limit": limit * 3},
			as_dict=True,
		)
	seen, out = set(), []
	for r in rows:
		if r.session in seen:
			continue
		seen.add(r.session)
		out.append({"session": r.session, "snippet": _snippet(r.content, query)})
		if len(out) >= limit:
			break
	return out


@frappe.whitelist()
def search_messages(query=None, limit=20):
	_ensure_user()
	query = (query or "").strip()[:200]
	if not query:
		return ok([])
	hits = _message_hits(query, frappe.session.user, max(1, min(frappe.utils.cint(limit) or 20, 50)))
	for h in hits:
		h["title"] = frappe.db.get_value("AI Chat Session", h["session"], "title")
	return ok(hits)


@frappe.whitelist()
def list_commands():
	_ensure_user()
	load_all()
	out = []
	for c in get_commands():
		req = c.get("required_doctypes") or []
		if any(not frappe.db.exists("DocType", d) for d in req):
			continue
		if any(not frappe.has_permission(d, "read") for d in req):
			continue
		out.append(c)
	# help always
	if not any(c.get("name") == "help" for c in out):
		out.append({"name": "help", "label": "Help", "description": "Show commands"})
	return ok(out)


@frappe.whitelist()
def new_session(title=None, assistant_mode=None, language=None):
	_ensure_user()
	name = _create_session(title=title, assistant_mode=assistant_mode, language=language)
	return ok({"name": name})


@frappe.whitelist()
def set_language(session=None, language=None):
	_ensure_user()
	if not session:
		return fail("session required")
	_assert_session_access(session)
	from zatgo_core.chat_ai.core.i18n import normalize_language

	doc = frappe.get_doc("AI Chat Session", session)
	doc.language = normalize_language(language)
	doc.save(ignore_permissions=True)
	return ok({"language": doc.language})


@frappe.whitelist()
def get_ui_locale():
	"""Language/voice prefs for the Desk sidebar."""
	_ensure_user()
	from zatgo_core.chat_ai.core.i18n import LANGUAGES, normalize_language

	lang = "en"
	voice_in = 1
	voice_out = 1
	auto_speak = 0
	tts_engine = "Voicebox"
	voicebox_url = "http://127.0.0.1:17493"
	voicebox_profile = ""
	voicebox_engine = ""
	voicebox_via_server = 0
	try:
		lang = normalize_language(frappe.db.get_single_value("Chat AI Settings", "default_language"))
		voice_in = int(frappe.db.get_single_value("Chat AI Settings", "enable_voice_input") or 0)
		voice_out = int(frappe.db.get_single_value("Chat AI Settings", "enable_voice_output") or 0)
		auto_speak = int(frappe.db.get_single_value("Chat AI Settings", "auto_speak_replies") or 0)
		tts_engine = frappe.db.get_single_value("Chat AI Settings", "tts_engine") or "Voicebox"
		voicebox_url = frappe.db.get_single_value("Chat AI Settings", "voicebox_url") or voicebox_url
		voicebox_profile = frappe.db.get_single_value("Chat AI Settings", "voicebox_profile") or ""
		voicebox_engine = frappe.db.get_single_value("Chat AI Settings", "voicebox_engine") or ""
		voicebox_via_server = int(frappe.db.get_single_value("Chat AI Settings", "voicebox_via_server") or 0)
	except Exception:
		pass
	return ok(
		{
			"language": lang,
			"languages": [
				{"code": m["code"], "label": m["label"], "native": m["native"], "bcp47": m["bcp47"], "dir": m["dir"]}
				for m in LANGUAGES.values()
			],
			"enable_voice_input": voice_in,
			"enable_voice_output": voice_out,
			"auto_speak_replies": auto_speak,
			"tts_engine": tts_engine,
			"voicebox_url": voicebox_url,
			"voicebox_profile": voicebox_profile,
			"voicebox_engine": voicebox_engine,
			"voicebox_via_server": voicebox_via_server,
		}
	)


def _create_session(title=None, assistant_mode=None, language=None):
	from zatgo_core.chat_ai.core.i18n import normalize_language

	settings_mode = None
	settings_lang = "en"
	try:
		settings_mode = frappe.db.get_single_value("Chat AI Settings", "default_assistant_mode")
		settings_lang = normalize_language(frappe.db.get_single_value("Chat AI Settings", "default_language"))
	except Exception:
		pass
	doc = frappe.get_doc(
		{
			"doctype": "AI Chat Session",
			"title": title or "New chat",
			"user": frappe.session.user,
			"assistant_mode": assistant_mode or settings_mode or "ERP Assistant",
			"language": normalize_language(language or settings_lang),
			"status": "Active",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _assert_session_access(session):
	if not session:
		frappe.throw(_("session required"))
	user = frappe.db.get_value("AI Chat Session", session, "user")
	if user != frappe.session.user and "System Manager" not in frappe.get_roles() and "Chat AI Manager" not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _message_in_session(message, session):
	row = frappe.db.get_value("AI Chat Message", message, ["session", "role", "content", "attachments"], as_dict=True)
	if not row or row.session != session:
		frappe.throw(_("Message not found"), frappe.DoesNotExistError)
	return row


@frappe.whitelist()
def regenerate(session=None, model=None, web=None):
	"""Re-answer the last user message: drops the answer(s) after it and runs the turn again."""
	_ensure_user()
	_assert_session_access(session)
	last = frappe.get_all(
		"AI Chat Message", filters={"session": session, "role": "user"}, fields=["name", "content", "attachments"],
		order_by="creation desc", limit_page_length=1,
	)
	if not last:
		return fail(_("Nothing to regenerate"), code="invalid")
	from zatgo_core.chat_ai.erpnext.sessions import truncate_from

	truncate_from(session, last[0].name, inclusive=False)
	attachments = [a["name"] for a in json.loads(last[0].attachments or "[]")] if last[0].attachments else []
	return send(session=session, message=last[0].content, attachments=attachments, model=model, web=web, regenerate=1)


@frappe.whitelist()
def edit_message(session=None, message=None, content=None, model=None, web=None):
	"""Replace a user message and re-run from there; later messages are discarded."""
	_ensure_user()
	_assert_session_access(session)
	row = _message_in_session(message, session)
	if row.role != "user" or not (content or "").strip():
		return fail(_("Only your own non-empty messages can be edited"), code="invalid")
	from zatgo_core.chat_ai.erpnext.sessions import truncate_from

	attachments = [a["name"] for a in json.loads(row.attachments or "[]")] if row.attachments else []
	truncate_from(session, message, inclusive=True)
	return send(session=session, message=content, attachments=attachments, model=model, web=web)


@frappe.whitelist()
def delete_message(session=None, message=None):
	_ensure_user()
	_assert_session_access(session)
	_message_in_session(message, session)
	frappe.db.delete("AI Artifact", {"message": message})
	frappe.db.delete("AI Chat Message", {"name": message})
	return ok({"deleted": message})


@frappe.whitelist()
def export_session(session=None):
	"""The conversation as Markdown, for copy / download / sharing outside the app."""
	_ensure_user()
	_assert_session_access(session)
	title = frappe.db.get_value("AI Chat Session", session, "title") or "Chat"
	rows = frappe.get_all(
		"AI Chat Message", filters={"session": session, "role": ("in", ["user", "assistant"])},
		fields=["role", "content", "creation"], order_by="creation asc", limit_page_length=2000,
	)
	parts = [f"# {title}"]
	for r in rows:
		who = "You" if r.role == "user" else "Assistant"
		parts.append(f"**{who}** · {frappe.utils.format_datetime(r.creation)}\n\n{r.content}")
	return ok({"title": title, "markdown": "\n\n---\n\n".join(parts)})


def _uploaded_file():
	request = getattr(frappe.local, "request", None)
	return (getattr(request, "files", None) or {}).get("file")


@frappe.whitelist()
def upload(session=None):
	"""Multipart upload (field `file`) into a conversation; creates the conversation if none is given."""
	_ensure_user()
	from zatgo_core.chat_ai.core.files.validate import UploadError
	from zatgo_core.chat_ai.erpnext import attachments as attachments_svc

	f = _uploaded_file()
	if not f:
		return fail(_("No file received"), code="no_file")
	try:
		enforce_upload()
		if session:
			_assert_session_access(session)
		max_mb = frappe.utils.cint(frappe.db.get_single_value("Chat AI Settings", "max_upload_mb") or 15)
		content = f.stream.read(max_mb * 1024 * 1024 + 1)  # never buffer more than the limit allows
		if not session:
			session = _create_session()
		data = attachments_svc.upload(session, f.filename, content)
		return ok({"session": session, **data})
	except QuotaExceeded as exc:
		return fail(str(exc), code="rate_limited")
	except UploadError as exc:
		return fail(str(exc), code=exc.code)


@frappe.whitelist()
def delete_attachment(attachment=None):
	_ensure_user()
	from zatgo_core.chat_ai.erpnext import attachments as attachments_svc

	attachments_svc.delete(attachment)
	return ok({"deleted": attachment})


@frappe.whitelist()
def list_models():
	"""What the composer can offer: selectable models and which features are usable."""
	_ensure_user()
	from zatgo_core.chat_ai.core.providers.registry import get_capabilities
	from zatgo_core.chat_ai.core.routing import SLOTS, allowed_models
	from zatgo_core.chat_ai.erpnext.settings import get_settings_dict

	s = get_settings_dict()
	slot_of = {(s.get(k) or "").strip(): k.removeprefix("model_") for k in SLOTS if (s.get(k) or "").strip()}
	default = (s.get("default_model") or "").strip()
	caps = get_capabilities(s.get("provider") or "OpenAI").as_dict()
	models = [
		{"name": m, "slot": "balanced" if m == default else slot_of.get(m, "fallback"), "default": m == default}
		for m in allowed_models(s)
	]
	return ok(
		{
			"models": models,
			"provider": s.get("provider"),
			"capabilities": caps,
			"routing": bool(s.get("enable_model_routing")),
			"features": {
				"file_upload": bool(s.get("enable_file_upload", 1)),
				"vision": bool(s.get("enable_vision", 1)) and caps.get("vision", False),
				"web_search": bool(s.get("enable_web_search") and s.get("web_search_api_key")),
				"streaming": bool(s.get("enable_streaming", 1)),
			},
			"max_upload_mb": frappe.utils.cint(s.get("max_upload_mb") or 15),
		}
	)
