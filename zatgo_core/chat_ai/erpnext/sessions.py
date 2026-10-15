"""Session lifecycle helpers shared by the API and the retention job."""

from __future__ import annotations

import frappe

from zatgo_core.chat_ai.erpnext import attachments

# Content that belongs to a conversation and goes with it. AI Tool Log is the
# audit trail and is deliberately kept (its session link may dangle).
SESSION_CONTENT = ("AI Chat Message", "AI Chat Memory", "AI Conversation Summary", "AI Artifact")


def purge_session(session: str) -> None:
	"""Delete a conversation and everything stored for it, files included."""
	attachments.delete_session_attachments(session)
	for doctype in SESSION_CONTENT:
		frappe.db.delete(doctype, {"session": session})
	frappe.db.delete("AI Chat Session", {"name": session})


def truncate_from(session: str, message: str, *, inclusive: bool) -> int:
	"""Delete the messages of `session` created at/after (or strictly after) `message`.
	Returns how many were removed."""
	created = frappe.db.get_value("AI Chat Message", {"name": message, "session": session}, "creation")
	if not created:
		frappe.throw("Message not found", frappe.DoesNotExistError)
	op = ">=" if inclusive else ">"
	names = frappe.get_all(
		"AI Chat Message", filters={"session": session, "creation": (op, created)}, pluck="name"
	)
	if not inclusive:
		names = [n for n in names if n != message]
	for n in names:
		frappe.db.delete("AI Artifact", {"message": n})
		frappe.db.delete("AI Chat Message", {"name": n})
	return len(names)
