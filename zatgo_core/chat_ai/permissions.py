"""Owner scoping for Chat AI's per-user doctypes.

Chat AI User holds rwcd on sessions/messages/memory, so role permissions alone
would let any chat user read another user's conversation through the Desk list
view or the REST resource API. These hooks restrict rows to their owner;
System Manager, Chat AI Manager and Administrator see everything (dashboards,
support, retention jobs).

Registered per doctype in hooks.py. The "module switched off" gate stays in
services/bundled_apps.py ("*" hooks) and is not repeated here.
"""

from __future__ import annotations

import frappe

MANAGER_ROLES = {"System Manager", "Chat AI Manager"}

# doctype -> ("user", fieldname)           row owned directly
#         -> ("session", fieldname)         row owned through its AI Chat Session
OWNER_FIELD: dict[str, tuple[str, str]] = {
	"AI Chat Session": ("user", "user"),
	"AI Chat Memory": ("user", "user"),
	"AI Artifact": ("user", "user"),
	"AI Tool Log": ("user", "user"),
	"AI Usage Daily": ("user", "user"),
	"AI Chat Message": ("session", "session"),
	"AI Attachment": ("session", "session"),
	"AI Scheduled Task": ("user", "user"),
	"AI Conversation Summary": ("session", "session"),
}


def _is_manager(user: str) -> bool:
	if user == "Administrator":
		return True
	return bool(MANAGER_ROLES & set(frappe.get_roles(user)))


def owner_query(doctype: str, user: str | None = None) -> str:
	"""SQL condition limiting `doctype` rows to the user's own."""
	user = user or frappe.session.user
	if _is_manager(user):
		return ""
	kind, field = OWNER_FIELD[doctype]
	quoted = frappe.db.escape(user)
	if kind == "user":
		return f"`tab{doctype}`.`{field}` = {quoted}"
	return (
		f"`tab{doctype}`.`{field}` in "
		f"(select `name` from `tabAI Chat Session` where `user` = {quoted})"
	)


def owner_has_permission(doc, user: str | None = None, doctype: str | None = None) -> bool:
	"""False only when the row belongs to somebody else and the user is no
	manager. Never None -- Frappe reads None as a denial."""
	user = user or frappe.session.user
	if _is_manager(user):
		return True
	doctype = doctype or getattr(doc, "doctype", None)
	spec = OWNER_FIELD.get(doctype)
	if not spec:
		return True
	kind, field = spec
	value = doc.get(field) if hasattr(doc, "get") else getattr(doc, field, None)
	if not value:
		# New, unsaved document: ownership is stamped by the server on insert.
		return True
	if kind == "user":
		return value == user
	return frappe.db.get_value("AI Chat Session", value, "user") == user


def _query(doctype):
	def fn(user=None):
		return owner_query(doctype, user)

	fn.__name__ = "query_" + doctype.lower().replace(" ", "_")
	return fn


def _perm(doctype):
	def fn(doc, user=None, permission_type=None):
		return owner_has_permission(doc, user=user, doctype=doctype)

	fn.__name__ = "has_perm_" + doctype.lower().replace(" ", "_")
	return fn


query_ai_chat_session = _query("AI Chat Session")
query_ai_chat_memory = _query("AI Chat Memory")
query_ai_artifact = _query("AI Artifact")
query_ai_tool_log = _query("AI Tool Log")
query_ai_usage_daily = _query("AI Usage Daily")
query_ai_chat_message = _query("AI Chat Message")
query_ai_conversation_summary = _query("AI Conversation Summary")
query_ai_attachment = _query("AI Attachment")
query_ai_scheduled_task = _query("AI Scheduled Task")

perm_ai_chat_session = _perm("AI Chat Session")
perm_ai_chat_memory = _perm("AI Chat Memory")
perm_ai_artifact = _perm("AI Artifact")
perm_ai_tool_log = _perm("AI Tool Log")
perm_ai_usage_daily = _perm("AI Usage Daily")
perm_ai_chat_message = _perm("AI Chat Message")
perm_ai_conversation_summary = _perm("AI Conversation Summary")
perm_ai_attachment = _perm("AI Attachment")
perm_ai_scheduled_task = _perm("AI Scheduled Task")
