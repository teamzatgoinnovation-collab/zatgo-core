# Copyright (c) 2026, ZatGo Innovation and contributors
# License: MIT

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, validate_email_address

from zatgo_core.chat_ai.core.schedule import FREQUENCIES, next_run_after

MAX_PROMPT_CHARS = 4000
MANAGERS = {"System Manager", "Chat AI Manager"}


def _is_manager(user: str) -> bool:
	return user == "Administrator" or bool(MANAGERS & set(frappe.get_roles(user)))


class AIScheduledTask(Document):
	def validate(self):
		self.title = (self.title or "").strip()
		self.prompt = (self.prompt or "").strip()
		self.user = self.user or frappe.session.user
		self._check_owner()
		if not self.prompt or len(self.prompt) > MAX_PROMPT_CHARS:
			frappe.throw(_("The instruction must be 1 to {0} characters.").format(MAX_PROMPT_CHARS))
		if self.frequency not in FREQUENCIES:
			frappe.throw(_("Choose how often the task repeats."))
		self._check_recipients()
		self._check_limit()
		if self.is_new() or self._schedule_changed():
			if self.enabled:
				self.consecutive_failures = 0
				self.next_run = next_run_after(
					self.frequency, now_datetime(), self.time_of_day, self.weekday, self.day_of_month
				)
		if not self.enabled:
			self.next_run = None

	def _schedule_changed(self) -> bool:
		before = self.get_doc_before_save()
		if not before:
			return True
		fields = ("enabled", "frequency", "time_of_day", "weekday", "day_of_month")
		return any(self.get(f) != before.get(f) for f in fields)

	def _check_owner(self):
		if self.user != frappe.session.user and not _is_manager(frappe.session.user):
			frappe.throw(_("You can only schedule tasks for yourself."), frappe.PermissionError)
		if not frappe.db.get_value("User", self.user, "enabled"):
			frappe.throw(_("{0} is not an active user.").format(self.user))

	def _check_recipients(self):
		raw = (self.email_recipients or "").strip()
		if not raw:
			return
		emails = [e.strip().lower() for e in re.split(r"[,\n;]", raw) if e.strip()]
		for e in emails:
			if not validate_email_address(e):
				frappe.throw(_("'{0}' is not a valid email address.").format(e))
			if not _is_manager(frappe.session.user) and not frappe.db.get_value("User", {"name": e, "enabled": 1}):
				frappe.throw(_("Results can only be emailed to active users ({0}). Ask a manager to add other addresses.").format(e))
		self.email_recipients = ", ".join(dict.fromkeys(emails))

	def _check_limit(self):
		if not self.enabled:
			return
		cap = frappe.utils.cint(frappe.conf.get("chat_ai_max_scheduled_tasks", 10))
		if cap <= 0:
			return
		others = frappe.db.count(
			"AI Scheduled Task", {"user": self.user, "enabled": 1, "name": ("!=", self.name or "")}
		)
		if others >= cap:
			frappe.throw(_("You already have {0} active scheduled tasks. Switch one off first.").format(cap))
