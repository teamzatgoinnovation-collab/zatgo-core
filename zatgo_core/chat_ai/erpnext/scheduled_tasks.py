"""Scheduled, read-only ZatGo AI tasks: pick up due tasks, run them as their owner, deliver the result.

Safety model
- A task runs as its `user`: every tool applies that user's permissions.
- The run is `unattended`: only read-category tools exist for it (orchestrator.run_turn).
- Usage quotas apply; a task that hits them is skipped, not run anyway.
- Claiming a due task is one atomic UPDATE (Idle -> Queued) that also moves next_run on, so two
  scheduler ticks (or workers) can never run the same occurrence twice.
- Three failures in a row switch the task off and tell its owner.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from zatgo_core.chat_ai.core.providers.errors import ProviderError
from zatgo_core.chat_ai.core.schedule import next_run_after

DOCTYPE = "AI Scheduled Task"
STUCK_AFTER_MINUTES = 45
MAX_FAILURES = 3
MAX_RESULT_CHARS = 60000


def _next(task, after=None):
	return next_run_after(task.frequency, after or now_datetime(), task.time_of_day, task.weekday, task.day_of_month)


def run_due(now=None, limit: int = 20) -> list[str]:
	"""Scheduler tick: queue what is due. Returns the names queued."""
	now = now or now_datetime()
	_release_stuck(now)
	names = frappe.get_all(
		DOCTYPE, filters={"enabled": 1, "run_state": "Idle", "next_run": ("<=", now)},
		pluck="name", order_by="next_run asc", limit_page_length=limit,
	)
	return [n for n in names if _claim(n, advance=True, now=now)]


def _release_stuck(now) -> None:
	"""A worker that died mid-run must not block its task forever."""
	cutoff = add_to_date(now, minutes=-STUCK_AFTER_MINUTES)
	frappe.db.sql(
		f"update `tab{DOCTYPE}` set run_state = 'Idle' where run_state != 'Idle' and modified < %s", (cutoff,)
	)


def _claim(name: str, *, advance: bool, now=None) -> bool:
	"""Atomically Idle -> Queued (and move next_run on); True if this caller won."""
	task = frappe.get_doc(DOCTYPE, name)
	nxt = _next(task, now) if advance else task.next_run
	frappe.db.sql(
		f"update `tab{DOCTYPE}` set run_state = 'Queued', next_run = %s, modified = %s "
		"where name = %s and run_state = 'Idle'",
		(nxt, now_datetime(), name),
	)
	if not frappe.db.sql("select row_count()")[0][0]:
		return False
	frappe.enqueue(
		"zatgo_core.chat_ai.erpnext.scheduled_tasks.execute",
		queue="long", timeout=900, name=name, enqueue_after_commit=True,
	)
	return True


def run_now(name: str) -> bool:
	"""Run a task once, outside its schedule (the owner or a manager)."""
	task = frappe.get_doc(DOCTYPE, name)
	task.check_permission("read")
	return _claim(name, advance=False)


def execute(name: str) -> dict:
	"""Run one queued task as its owner. Never raises: the outcome is recorded on the task."""
	from zatgo_core.chat_ai.core import quota
	from zatgo_core.chat_ai.erpnext.orchestrator import run_turn

	task = frappe.get_doc(DOCTYPE, name)
	if task.run_state != "Queued":
		return {"skipped": "not queued"}
	original_user = frappe.session.user
	status, error, result = "Success", "", ""
	frappe.db.set_value(DOCTYPE, name, "run_state", "Running")
	frappe.db.commit()
	try:
		frappe.set_user(task.user)
		quota._check_daily(task.user)
		quota._check_tokens(task.user)
		session = _session_for(task)
		data = run_turn(
			session_name=session, user_message=task.prompt, execution_mode="_worker", unattended=True,
		)
		result = (data.get("content") or "").strip()[:MAX_RESULT_CHARS]
		if not result:
			status, error = "Failed", _("The assistant returned no answer.")
	except quota.QuotaExceeded as exc:
		status, error = "Skipped", str(exc)
	except ProviderError as exc:
		status, error = "Failed", exc.message
		frappe.log_error(title=f"chat_ai scheduled task provider {exc.code}", message=exc.detail or str(exc))
	except Exception:
		status, error = "Failed", _("The task could not be completed.")
		frappe.log_error(title="chat_ai scheduled task")
	finally:
		frappe.set_user(original_user)
	_record(task, status, error, result)
	return {"status": status}


def _session_for(task) -> str:
	if task.session and frappe.db.exists("AI Chat Session", task.session):
		return task.session
	doc = frappe.get_doc(
		{"doctype": "AI Chat Session", "title": f"Scheduled: {task.title}"[:140], "user": task.user, "status": "Active"}
	)
	doc.owner = task.user
	doc.insert(ignore_permissions=True)
	frappe.db.set_value(DOCTYPE, task.name, "session", doc.name)
	task.session = doc.name
	return doc.name


def _record(task, status: str, error: str, result: str) -> None:
	failures = 0 if status != "Failed" else cint(task.consecutive_failures) + 1
	disable = failures >= MAX_FAILURES
	values = {
		"run_state": "Idle", "last_run": now_datetime(), "last_status": status, "last_error": (error or "")[:500],
		"run_count": cint(task.run_count) + 1, "consecutive_failures": failures,
	}
	if result:
		values["last_result"] = result
	if disable:
		values.update(enabled=0, next_run=None)
	frappe.db.set_value(DOCTYPE, task.name, values, update_modified=False)
	try:
		_deliver(task, status, error, result, disabled=disable)
	except Exception:
		frappe.log_error(title="chat_ai scheduled task delivery")
	frappe.db.commit()


def _deliver(task, status: str, error: str, result: str, *, disabled: bool) -> None:
	if status == "Success":
		subject = _("ZatGo AI: {0}").format(task.title)
		body = result
	elif disabled:
		subject = _("ZatGo AI task switched off: {0}").format(task.title)
		body = _("The task failed {0} times in a row ({1}) and was switched off. Fix the cause, then enable it again.").format(MAX_FAILURES, error)
	elif status == "Skipped":
		subject = _("ZatGo AI task skipped: {0}").format(task.title)
		body = error
	else:
		return  # a single failure is shown on the task itself; no noise
	frappe.get_doc(
		{
			"doctype": "Notification Log", "subject": subject, "for_user": task.user, "type": "Alert",
			"document_type": "AI Chat Session" if task.session else DOCTYPE,
			"document_name": task.session or task.name,
			"email_content": frappe.utils.md_to_html(body),
		}
	).insert(ignore_permissions=True)
	recipients = [e.strip() for e in (task.email_recipients or "").split(",") if e.strip()]
	if recipients and status == "Success":
		frappe.sendmail(recipients=recipients, subject=subject, message=frappe.utils.md_to_html(body), delayed=True)
