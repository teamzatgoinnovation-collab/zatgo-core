"""Whitelisted chat API."""

from __future__ import annotations

import json

import frappe
from frappe import _

from zatgo_core.chat_ai.api.response import fail, ok
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
):
	_ensure_user()
	if isinstance(client_context, str):
		client_context = json.loads(client_context or "{}")
	if isinstance(pending_args, str):
		pending_args = json.loads(pending_args or "{}")
	message = message or ""
	if not session:
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
		)
		return ok(data)
	except Exception as exc:
		frappe.log_error(title="chat_ai.send")
		return fail(str(exc))


@frappe.whitelist()
def cancel(session=None):
	_ensure_user()
	_assert_session_access(session)
	from zatgo_core.chat_ai.core.tool_pipeline import request_cancel

	request_cancel(session)
	return ok({"cancelled": True})


@frappe.whitelist()
def history(session=None, limit=50):
	_ensure_user()
	if not session:
		return fail("session required")
	_assert_session_access(session)
	rows = frappe.get_all(
		"AI Chat Message",
		filters={"session": session},
		fields=["name", "role", "content", "content_json", "creation", "tokens_in", "tokens_out"],
		order_by="creation asc",
		limit_page_length=int(limit or 50),
	)
	return ok(rows)


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
	frappe.delete_doc("AI Chat Session", session, ignore_permissions=True, force=True)
	return ok({"deleted": session})


@frappe.whitelist()
def search_sessions(query=None):
	_ensure_user()
	q = f"%{query or ''}%"
	rows = frappe.get_all(
		"AI Chat Session",
		filters={"user": frappe.session.user, "title": ("like", q)},
		fields=["name", "title", "assistant_mode", "status", "is_pinned", "last_message_at"],
		limit_page_length=50,
	)
	return ok(rows)


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
