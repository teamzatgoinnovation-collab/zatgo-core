"""Per-user request limits for chat sends.

Daily cap: Chat AI Settings.max_messages_per_user_per_day (0/empty = no cap),
counted from AI Usage Daily. Burst cap: a short sliding window in the cache,
default 20 sends per minute, overridable with `chat_ai_max_per_minute` in
site_config (0 disables).
"""

from __future__ import annotations

import time

import frappe
from frappe import _

DEFAULT_PER_MINUTE = 20
WINDOW_SEC = 60


class QuotaExceeded(frappe.ValidationError):
	http_status_code = 429


def _burst_limit() -> int:
	return frappe.utils.cint(frappe.conf.get("chat_ai_max_per_minute", DEFAULT_PER_MINUTE))


def _check_burst(user: str) -> None:
	limit = _burst_limit()
	if limit <= 0:
		return
	key = f"chat_ai_rate:{user}"
	now = time.time()
	hits = [t for t in (frappe.cache.get_value(key) or []) if now - t < WINDOW_SEC]
	if len(hits) >= limit:
		raise QuotaExceeded(_("You are sending messages too quickly. Please wait a moment and try again."))
	hits.append(now)
	frappe.cache.set_value(key, hits, expires_in_sec=WINDOW_SEC)


def _check_daily(user: str) -> None:
	cap = frappe.utils.cint(frappe.db.get_single_value("Chat AI Settings", "max_messages_per_user_per_day"))
	if cap <= 0:
		return
	used = frappe.db.sql(
		"select coalesce(sum(request_count), 0) from `tabAI Usage Daily` where user = %s and usage_date = %s",
		(user, frappe.utils.today()),
	)[0][0]
	if frappe.utils.cint(used) >= cap:
		raise QuotaExceeded(_("Daily message limit reached. It resets tomorrow."))


def enforce(user: str | None = None) -> None:
	"""Raise QuotaExceeded when the user is over a limit; otherwise count the send."""
	user = user or frappe.session.user
	_check_daily(user)
	_check_burst(user)
