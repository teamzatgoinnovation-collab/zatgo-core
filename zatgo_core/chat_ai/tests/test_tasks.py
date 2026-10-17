"""Scheduled, read-only ZatGo AI tasks: schedule maths, validation, scheduling, execution, safety.

Run: bench --site <site> run-tests --app zatgo_core --module zatgo_core.chat_ai.tests.test_tasks
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, time, timedelta
from unittest import mock

import frappe

from zatgo_core.chat_ai.core.schedule import next_run_after, to_time
from zatgo_core.chat_ai.erpnext import scheduled_tasks as st
from zatgo_core.chat_ai.tests.test_flow import JSON, FlowCase, completion, error, plan, stream, stream_tool_call


def tool_completion(name, args):
	"""A non-streaming completion whose message is a tool call (unattended runs do not stream)."""
	body = {"model": "m", "usage": {"prompt_tokens": 9, "completion_tokens": 3}, "choices": [{"finish_reason": "tool_calls", "message": {
		"role": "assistant", "content": None,
		"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}
	return (200, JSON, json.dumps(body).encode())


class TestSchedule(unittest.TestCase):
	def dt(self, *a):
		return datetime(*a)

	def test_hourly_is_the_next_top_of_the_hour(self):
		self.assertEqual(next_run_after("Hourly", self.dt(2026, 10, 17, 9, 30, 12)), self.dt(2026, 10, 17, 10))
		self.assertEqual(next_run_after("Hourly", self.dt(2026, 10, 17, 23, 0, 0)), self.dt(2026, 10, 18, 0))  # strictly after

	def test_daily_today_if_still_ahead_else_tomorrow(self):
		self.assertEqual(next_run_after("Daily", self.dt(2026, 10, 17, 7, 59), "08:00"), self.dt(2026, 10, 17, 8))
		self.assertEqual(next_run_after("Daily", self.dt(2026, 10, 17, 8, 0), "08:00"), self.dt(2026, 10, 18, 8))
		self.assertEqual(next_run_after("Daily", self.dt(2026, 12, 31, 20), "06:30:15"), self.dt(2027, 1, 1, 6, 30, 15))

	def test_weekly(self):
		sat = self.dt(2026, 10, 17, 12)  # a Saturday
		self.assertEqual(sat.strftime("%A"), "Saturday")
		self.assertEqual(next_run_after("Weekly", sat, "09:00", "Monday"), self.dt(2026, 10, 19, 9))
		self.assertEqual(next_run_after("Weekly", sat, "13:00", "Saturday"), self.dt(2026, 10, 17, 13))  # later today
		self.assertEqual(next_run_after("Weekly", sat, "09:00", "Saturday"), self.dt(2026, 10, 24, 9))  # already passed
		self.assertEqual(next_run_after("Weekly", sat, "09:00", "Friday"), self.dt(2026, 10, 23, 9))

	def test_monthly_clamps_to_28_and_rolls_the_year(self):
		self.assertEqual(next_run_after("Monthly", self.dt(2026, 10, 5, 12), "08:00", day_of_month=15), self.dt(2026, 10, 15, 8))
		self.assertEqual(next_run_after("Monthly", self.dt(2026, 10, 20, 12), "08:00", day_of_month=15), self.dt(2026, 11, 15, 8))
		self.assertEqual(next_run_after("Monthly", self.dt(2026, 12, 20, 12), "08:00", day_of_month=15), self.dt(2027, 1, 15, 8))
		self.assertEqual(next_run_after("Monthly", self.dt(2026, 1, 30, 12), "08:00", day_of_month=31), self.dt(2026, 2, 28, 8))  # never skips February
		self.assertEqual(next_run_after("Monthly", self.dt(2026, 1, 30, 12), "08:00", day_of_month=0), self.dt(2026, 2, 1, 8))

	def test_time_inputs(self):
		self.assertEqual(to_time(timedelta(hours=8, minutes=5)), time(8, 5))
		self.assertEqual(to_time("8:5"), time(8, 5))
		self.assertEqual(to_time(time(7, 0)), time(7, 0))
		self.assertEqual(to_time(None), time(8, 0))
		self.assertEqual(to_time(timedelta(hours=25)), time(1, 0))  # wraps, never crashes

	def test_bad_input_is_rejected(self):
		with self.assertRaises(ValueError):
			next_run_after("Yearly", self.dt(2026, 1, 1))
		with self.assertRaises(ValueError):
			next_run_after("Weekly", self.dt(2026, 1, 1), weekday="Funday")


class TaskCase(FlowCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Notification Log", {"for_user": ("in", [self.owner, self.other]), "subject": ("like", "ZatGo AI%")})
		for name in frappe.get_all("AI Scheduled Task", filters={"user": ("in", [self.owner, self.other])}, pluck="name"):
			frappe.delete_doc("AI Scheduled Task", name, force=True, ignore_permissions=True)

	def make(self, user=None, **kw):
		user = user or self.owner
		values = {"doctype": "AI Scheduled Task", "title": "Low stock", "prompt": "Which items are below their reorder level?",
				  "frequency": "Daily", "time_of_day": "08:00:00", "user": user, **kw}
		frappe.set_user(user)
		try:
			return frappe.get_doc(values).insert()
		finally:
			frappe.set_user("Administrator")

	def queue(self, name):
		frappe.db.set_value("AI Scheduled Task", name, "run_state", "Queued")

	def reload(self, name):
		return frappe.get_doc("AI Scheduled Task", name)

	def notifications(self, user=None):
		return frappe.get_all("Notification Log", filters={"for_user": user or self.owner, "subject": ("like", "ZatGo AI%")}, fields=["subject", "document_name"])


class TestTaskValidation(TaskCase):
	def test_a_new_task_gets_its_next_run(self):
		t = self.make()
		self.assertGreater(t.next_run, frappe.utils.now_datetime())
		self.assertEqual((t.run_state, t.consecutive_failures, t.user), ("Idle", 0, self.owner))

	def test_users_can_only_schedule_for_themselves_managers_for_anyone(self):
		with self.assertRaises(frappe.PermissionError):
			self._as_creator(self.owner, self.other)
		frappe.set_user("Administrator")
		t = frappe.get_doc({"doctype": "AI Scheduled Task", "title": "for them", "prompt": "p", "frequency": "Daily", "user": self.other}).insert()
		self.assertEqual(t.user, self.other)

	def _as_creator(self, creator, target):
		frappe.set_user(creator)
		try:
			frappe.get_doc({"doctype": "AI Scheduled Task", "title": "sneaky", "prompt": "p", "frequency": "Daily", "user": target}).insert()
		finally:
			frappe.set_user("Administrator")

	def test_prompt_frequency_and_recipient_rules(self):
		with self.assertRaises(frappe.ValidationError):
			self.make(prompt="   ")
		with self.assertRaises(frappe.ValidationError):
			self.make(prompt="x" * 4001)
		with self.assertRaises(frappe.ValidationError):
			self.make(email_recipients="not-an-email")
		with self.assertRaises(frappe.ValidationError):  # a plain user cannot send data to an outside address
			self.make(email_recipients="outsider@evil.example")
		t = self.make(email_recipients=f"{self.owner.upper()}, {self.owner}")  # an enabled user, de-duplicated
		self.assertEqual(t.email_recipients, self.owner)
		frappe.set_user("Administrator")
		t2 = frappe.get_doc({"doctype": "AI Scheduled Task", "title": "m", "prompt": "p", "frequency": "Daily", "user": self.owner,
							 "email_recipients": "accountant@client.example"}).insert()
		self.assertEqual(t2.email_recipients, "accountant@client.example")  # managers may

	def test_active_task_limit_per_user(self):
		with mock.patch.dict(frappe.conf, {"chat_ai_max_scheduled_tasks": 2}):
			self.make(title="a")
			self.make(title="b")
			with self.assertRaises(frappe.ValidationError):
				self.make(title="c")
			frappe.set_user(self.owner)
			frappe.db.set_value("AI Scheduled Task", frappe.get_all("AI Scheduled Task", filters={"user": self.owner}, pluck="name")[0], "enabled", 0)
			frappe.set_user("Administrator")
			self.make(title="d")  # a disabled one frees a slot

	def test_schedule_changes_recompute_and_disabling_clears(self):
		t = self.make(frequency="Daily", time_of_day="08:00:00")
		first = t.next_run
		frappe.set_user("Administrator")
		t.frequency, t.weekday = "Weekly", "Friday"
		t.save()
		self.assertNotEqual(t.next_run, first)
		self.assertEqual(t.next_run.strftime("%A"), "Friday")
		t.enabled = 0
		t.save()
		self.assertIsNone(t.next_run)
		t.consecutive_failures = 2
		t.enabled = 1
		t.save()
		self.assertEqual(t.consecutive_failures, 0)  # switching it on again is a fresh start
		self.assertIsNotNone(t.next_run)

	def test_owner_scoping(self):
		t = self.make()
		frappe.set_user(self.other)
		self.assertNotIn(t.name, frappe.get_list("AI Scheduled Task", pluck="name"))
		self.assertFalse(frappe.has_permission("AI Scheduled Task", "read", doc=t.name))
		frappe.set_user(self.owner)
		self.assertIn(t.name, frappe.get_list("AI Scheduled Task", pluck="name"))


class TestScheduling(TaskCase):
	def test_due_tasks_are_queued_exactly_once_and_moved_on(self):
		t = self.make()
		not_due = self.make(title="later")
		frappe.db.set_value("AI Scheduled Task", t.name, "next_run", frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-5))
		off = self.make(title="off")
		frappe.db.set_value("AI Scheduled Task", off.name, {"enabled": 0, "next_run": frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-5)})
		with mock.patch.object(frappe, "enqueue") as enqueue:
			self.assertEqual(st.run_due(), [t.name])
			self.assertEqual(st.run_due(), [])  # the next tick must not run the same occurrence again
		self.assertEqual(enqueue.call_count, 1)
		self.assertEqual(enqueue.call_args.kwargs["name"], t.name)
		row = self.reload(t.name)
		self.assertEqual(row.run_state, "Queued")
		self.assertGreater(row.next_run, frappe.utils.now_datetime())  # no catch-up storm after downtime
		self.assertEqual(self.reload(not_due.name).run_state, "Idle")
		self.assertEqual(self.reload(off.name).run_state, "Idle")

	def test_a_worker_that_died_does_not_block_its_task_forever(self):
		t = self.make()
		frappe.db.sql("update `tabAI Scheduled Task` set run_state='Running', modified=%s where name=%s",
					  (frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-st.STUCK_AFTER_MINUTES - 5), t.name))
		with mock.patch.object(frappe, "enqueue"):
			st.run_due()
		self.assertEqual(self.reload(t.name).run_state, "Idle")

	def test_a_running_task_is_not_released_early(self):
		t = self.make()
		frappe.db.set_value("AI Scheduled Task", t.name, "run_state", "Running")
		with mock.patch.object(frappe, "enqueue"):
			st.run_due()
		self.assertEqual(self.reload(t.name).run_state, "Running")

	def test_run_now_is_owner_only_and_not_double_queued(self):
		from zatgo_core.chat_ai.api import tasks

		t = self.make()
		with mock.patch.object(frappe, "enqueue") as enqueue:
			frappe.set_user(self.other)
			with self.assertRaises(frappe.PermissionError):
				tasks.run_now(name=t.name)
			frappe.set_user(self.owner)
			self.assertTrue(tasks.run_now(name=t.name)["ok"])
			again = tasks.run_now(name=t.name)
		self.assertEqual((again["ok"], again["code"]), (False, "busy"))
		self.assertEqual(enqueue.call_count, 1)
		self.assertEqual(self.reload(t.name).next_run, t.next_run)  # a manual run does not shift the schedule
		frappe.set_user("Administrator")
		self.assertEqual(tasks.run_now(name="nope")["code"], "not_found")


class TestExecution(TaskCase):
	def test_success_records_delivers_and_keeps_history(self):
		self.provider(plan(), completion("Low stock: Bolts (3 left), Nuts (0 left)."))
		t = self.make(email_recipients=self.owner)
		self.queue(t.name)
		with mock.patch.object(frappe, "sendmail") as mail:
			out = st.execute(t.name)
		self.assertEqual(out["status"], "Success")
		row = self.reload(t.name)
		self.assertEqual((row.last_status, row.run_state, row.run_count, row.consecutive_failures), ("Success", "Idle", 1, 0))
		self.assertIn("Bolts", row.last_result)
		self.assertEqual(frappe.session.user, "Administrator")  # the worker's identity is restored
		msgs = frappe.get_all("AI Chat Message", filters={"session": row.session}, fields=["role", "content"], order_by="creation, role desc")
		self.assertEqual([m.role for m in msgs], ["user", "assistant"])
		self.assertEqual(frappe.db.get_value("AI Chat Session", row.session, "user"), self.owner)
		subjects = self.notifications()
		self.assertEqual([n.subject for n in subjects], ["ZatGo AI: Low stock"])
		self.assertEqual(subjects[0].document_name, row.session)
		mail.assert_called_once()
		self.assertEqual(mail.call_args.kwargs["recipients"], [self.owner])

	def test_every_run_reuses_the_conversation(self):
		self.provider(plan(), completion("one"), plan(), completion("two"))
		t = self.make()
		self.queue(t.name)
		st.execute(t.name)
		first = self.reload(t.name).session
		self.queue(t.name)
		st.execute(t.name)
		self.assertEqual(self.reload(t.name).session, first)
		self.assertEqual(frappe.db.count("AI Chat Message", {"session": first}), 4)

	def test_a_run_can_never_change_data_even_when_the_model_tries(self):
		before = frappe.db.count("AI Scheduled Task")
		srv = self.provider(
			plan(simple=False, tools=["schedule_report"], skills=["workspace"]),
			tool_completion("schedule_report", {"title": "persist me", "prompt": "do things", "frequency": "Hourly"}),
			completion("I could not schedule that."),
		)
		t = self.make()
		before += 1
		self.queue(t.name)
		self.assertEqual(st.execute(t.name)["status"], "Success")
		self.assertEqual(frappe.db.count("AI Scheduled Task"), before)  # no task scheduled another task
		tool_msg = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "tool"][0]
		self.assertFalse(json.loads(tool_msg["content"])["ok"])

	def test_plan_approval_is_not_asked_of_nobody(self):
		approval = json.dumps({"intent": "x", "is_simple_question": True, "needs_plan_approval": True, "risk_level": "high",
							   "candidate_skills": ["core"], "candidate_tools": [], "implementation_plan": ["a", "b"]})
		self.provider(completion(approval), completion("Report body."))
		t = self.make()
		self.queue(t.name)
		self.assertEqual(st.execute(t.name)["status"], "Success")
		self.assertEqual(self.reload(t.name).last_result, "Report body.")

	def test_failures_are_recorded_quietly_then_the_task_switches_itself_off(self):
		t = self.make()
		for n in range(1, st.MAX_FAILURES + 1):
			self.provider(error(500))
			self.queue(t.name)
			self.assertEqual(st.execute(t.name)["status"], "Failed")
			row = self.reload(t.name)
			self.assertEqual(row.consecutive_failures, n)
			self.assertNotIn("UPSTREAM", row.last_error or "")
			if n < st.MAX_FAILURES:
				self.assertEqual(self.notifications(), [])  # a single hiccup is not worth a notification
		self.assertEqual((row.enabled, row.next_run), (0, None))
		self.assertEqual([n.subject for n in self.notifications()], ["ZatGo AI task switched off: Low stock"])

	def test_a_success_resets_the_failure_count(self):
		t = self.make()
		self.provider(error(500))
		self.queue(t.name)
		st.execute(t.name)
		self.provider(plan(), completion("fine"))
		self.queue(t.name)
		st.execute(t.name)
		self.assertEqual(self.reload(t.name).consecutive_failures, 0)

	def test_usage_limits_apply_to_automatic_runs(self):
		srv = self.provider(plan(), completion("never"))
		t = self.make()
		frappe.get_doc({"doctype": "AI Usage Daily", "usage_date": frappe.utils.today(), "user": self.owner, "provider": "x", "model": "x", "request_count": 5}).insert(ignore_permissions=True)
		self.db_settings["max_messages_per_user_per_day"] = 1
		self.queue(t.name)
		self.assertEqual(st.execute(t.name)["status"], "Skipped")
		self.assertEqual(srv.requests, [])
		row = self.reload(t.name)
		self.assertEqual((row.last_status, row.consecutive_failures), ("Skipped", 0))  # skipping is not failing
		self.assertEqual([n.subject for n in self.notifications()], ["ZatGo AI task skipped: Low stock"])

	def test_only_queued_tasks_run(self):
		srv = self.provider(plan(), completion("never"))
		t = self.make()
		self.assertEqual(st.execute(t.name), {"skipped": "not queued"})
		self.assertEqual(srv.requests, [])

	def test_runs_use_the_owners_identity_and_permissions(self):
		seen = []
		from zatgo_core.chat_ai.erpnext import orchestrator

		def spy(**kw):
			seen.append((frappe.session.user, kw["unattended"], kw["execution_mode"]))
			return {"content": "ok"}

		t = self.make()
		self.queue(t.name)
		with mock.patch.object(orchestrator, "run_turn", side_effect=spy):
			st.execute(t.name)
		self.assertEqual(seen, [(self.owner, True, "_worker")])


class TestScheduleByChat(TaskCase):
	def test_asking_in_chat_creates_a_task_only_after_confirmation(self):
		self.provider(
			plan(simple=False, tools=["schedule_report"], skills=["workspace"]),
			stream_tool_call("schedule_report", {"title": "Morning stock", "prompt": "List items below reorder level",
												 "frequency": "Daily", "time_of_day": "07:30"}),
		)
		s = self.session()
		res = self.send(s, "Every morning at 7:30 tell me which items are low on stock")
		self.assertTrue(res["ok"], res)
		self.assertTrue(res["data"]["needs_confirmation"])  # nothing is created yet
		self.assertEqual(frappe.db.count("AI Scheduled Task", {"user": self.owner}), 0)
		res2 = self.send(s, "", confirmed=1, confirmation_token=res["data"]["confirmation_token"])
		self.assertTrue(res2["ok"], res2)
		tasks = frappe.get_all("AI Scheduled Task", filters={"user": self.owner}, fields=["title", "frequency", "time_of_day", "enabled", "next_run"])
		self.assertEqual([(x.title, x.frequency, x.enabled) for x in tasks], [("Morning stock", "Daily", 1)])
		self.assertEqual(str(tasks[0].time_of_day), "7:30:00")
		self.assertIsNotNone(tasks[0].next_run)


class TestStockTools(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_low_stock_uses_reorder_rules_and_orders_by_shortage(self):
		from zatgo_core.chat_ai.erpnext.skills.inventory import tools

		bins = [
			frappe._dict(item_code="BOLT", warehouse="Main", actual_qty=3, projected_qty=3),
			frappe._dict(item_code="NUT", warehouse="Main", actual_qty=0, projected_qty=-2),
			frappe._dict(item_code="WASHER", warehouse="Main", actual_qty=500, projected_qty=500),
			frappe._dict(item_code="NORULE", warehouse="Main", actual_qty=0, projected_qty=0),
			frappe._dict(item_code="BOLT", warehouse="Other", actual_qty=1, projected_qty=1),
		]
		rules = [
			frappe._dict(parent="BOLT", warehouse="Main", warehouse_reorder_level=10, warehouse_reorder_qty=50),
			frappe._dict(parent="NUT", warehouse="Main", warehouse_reorder_level=20, warehouse_reorder_qty=100),
			frappe._dict(parent="WASHER", warehouse="Main", warehouse_reorder_level=100, warehouse_reorder_qty=10),
		]
		with mock.patch.object(frappe, "get_list", return_value=bins), mock.patch.object(frappe, "get_all", return_value=rules):
			out = tools._low_stock_items()
			limited = tools._low_stock_items(limit=1)
		self.assertEqual([(r["item_code"], r["shortage"]) for r in out["rows"]], [("NUT", 22.0), ("BOLT", 7.0)])
		self.assertEqual(out["count"], 2)  # WASHER is fine, NORULE has no rule, BOLT/Other has none for that warehouse
		self.assertEqual((limited["count"], len(limited["rows"]), limited["truncated"]), (2, 1, True))

	def test_stock_balance_passes_filters_and_clamps_the_limit(self):
		from zatgo_core.chat_ai.erpnext.skills.inventory import tools

		rows = [frappe._dict(item_code="A", warehouse="W", actual_qty=5, reserved_qty=0, projected_qty=5)]
		with mock.patch.object(frappe, "get_list", return_value=rows) as gl:
			out = tools._stock_balance(warehouse="W", item_code="A", limit=100000)
		kw = gl.call_args.kwargs
		self.assertEqual(kw["filters"], {"warehouse": "W", "item_code": "A"})
		self.assertEqual(kw["limit_page_length"], tools.MAX_ROWS)
		self.assertEqual(out["count"], 1)
		self.assertEqual(tools._clamp("junk"), 50)

	def test_both_tools_are_read_only(self):
		from zatgo_core.chat_ai.core.tool_router.spec import CATEGORY_READ
		from zatgo_core.chat_ai.erpnext.skills.inventory import tools

		cats = {t.name: t.category for t in tools.get_tools()}
		self.assertEqual(cats["stock_balance"], CATEGORY_READ)
		self.assertEqual(cats["low_stock_items"], CATEGORY_READ)
