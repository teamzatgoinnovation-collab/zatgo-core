"""End-to-end: chat.send -> orchestrator -> provider -> streamed events -> DB.

The provider is a real local HTTP server speaking the OpenAI-compatible wire format; nothing
inside the module is mocked except settings, the module switch and realtime capture.
Turn anatomy: request 0 is always the planner (a plain JSON completion); then either a
streamed direct answer, or streamed tool-loop rounds.

Run: bench --site <site> run-tests --app zatgo_core --module zatgo_core.chat_ai.tests.test_flow
"""

from __future__ import annotations

import io
import json
from unittest import mock

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.chat_ai.api import chat
from zatgo_core.chat_ai.core.tool_pipeline import request_cancel
from zatgo_core.chat_ai.erpnext import attachments as att_svc
from zatgo_core.chat_ai.erpnext import orchestrator, sessions
from zatgo_core.chat_ai.erpnext.skills.workspace import tools as wtools
from zatgo_core.chat_ai.tests._servers import ScriptedServer, sse
from zatgo_core.chat_ai.tests.test_attachments import _docx, _png

JSON = "application/json"
SSE = "text/event-stream"


# -- wire helpers --------------------------------------------------------------------------------
def plan(simple=True, tools=(), skills=("core",)):
	body = {
		"intent": "x", "is_simple_question": simple, "risk_level": "low", "assumptions": [],
		"candidate_skills": list(skills), "candidate_tools": list(tools),
	}
	return completion(json.dumps(body), tokens=(5, 7))


def completion(text, tokens=(1, 1), model="m"):
	return (200, JSON, json.dumps({
		"model": model, "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
		"usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]},
	}).encode())


def stream(*parts, tokens=(11, 4), finish=True):
	frames = [(None, {"model": "m", "choices": [{"delta": {"content": p}}]}) for p in parts]
	if finish:
		frames += [(None, {"choices": [{"delta": {}, "finish_reason": "stop"}]}),
				   (None, {"choices": [], "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}}), (None, "[DONE]")]
	return (200, SSE, sse(*frames))


def stream_tool_call(name, args: dict, call_id="call_1", preface="", tokens=(20, 6)):
	raw = json.dumps(args)
	cut = max(1, len(raw) // 2)  # arguments arrive in fragments, like a real provider
	frames = []
	if preface:
		frames.append((None, {"choices": [{"delta": {"content": preface}}]}))
	frames += [
		(None, {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": call_id, "function": {"name": name, "arguments": raw[:cut]}}]}}]}),
		(None, {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": raw[cut:]}}]}}]}),
		(None, {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
		(None, {"choices": [], "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]}}),
		(None, "[DONE]"),
	]
	return (200, SSE, sse(*frames))


def error(status):
	return (status, JSON, json.dumps({"error": {"message": "UPSTREAM-SECRET-DETAIL sk-leak"}}).encode())


def _user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
						"roles": [{"role": "Chat AI User"}]}).insert(ignore_permissions=True)
	return email


class FlowCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.owner = _user("chat_flow_owner@example.com")
		cls.other = _user("chat_flow_other@example.com")
		cls.sessions: list[str] = []

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for s in cls.sessions:
			sessions.purge_session(s)
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self.servers: list[ScriptedServer] = []
		self.events: list[tuple[str, dict]] = []
		self.cfg: dict = {}
		for u in (self.owner, self.other):
			frappe.cache.delete_value(f"chat_ai_rate:{u}")
			frappe.cache.delete_value(f"chat_ai_upload_rate:{u}")
		self.db_settings: dict = {}
		real_get = frappe.db.get_single_value

		def get_single_value(doctype, field=None, *a, **kw):
			if doctype == "Chat AI Settings" and field in self.db_settings:
				return self.db_settings[field]
			return real_get(doctype, field, *a, **kw)

		gv = mock.patch.object(frappe.db, "get_single_value", side_effect=get_single_value)
		gv.start()
		self.addCleanup(gv.stop)
		rt = mock.patch.object(frappe, "publish_realtime", side_effect=lambda ev, msg=None, **kw: self.events.append((ev, msg or {})))
		rt.start()
		self.addCleanup(rt.stop)
		on = mock.patch("zatgo_core.services.bundled_apps.is_on", return_value=True)
		on.start()
		self.addCleanup(on.stop)
		# The skill loader re-executes each skill file as a fresh module every turn, so the tools
		# module binds get_settings_dict at that moment: patch the source as well as the importers.
		from zatgo_core.chat_ai.erpnext import settings as settings_mod

		for mod in (settings_mod, orchestrator, att_svc, wtools):
			p = mock.patch.object(mod, "get_settings_dict", side_effect=lambda: dict(self.cfg))
			p.start()
			self.addCleanup(p.stop)
		self.addCleanup(lambda: frappe.set_user("Administrator"))

	def tearDown(self):
		frappe.set_user("Administrator")
		for s in self.servers:
			s.stop()

	# -- builders --
	def fresh_user(self, tag):
		"""A user nobody has used in this test class (quota counters are per user)."""
		email = f"chat_flow_{tag}@example.com"
		_user(email)
		frappe.cache.delete_value(f"chat_ai_rate:{email}")
		frappe.db.delete("AI Usage Daily", {"user": email})
		return email

	def provider(self, *responses, **settings) -> ScriptedServer:
		srv = ScriptedServer(list(responses))
		self.servers.append(srv)
		self.cfg.update({
			"provider": "Custom OpenAI-compatible", "api_key": "test-key", "api_endpoint": srv.url + "/v1",
			"default_model": "m-main", "enable_streaming": 1, "enable_tool_calling": 1, "enable_file_upload": 1,
			"enable_vision": 1, "max_upload_mb": 20, "max_tool_rounds": 4, "enable_audit_logs": 1,
			"enable_conversation_memory": 0, "require_confirmation_for_writes": 1, "enable_event_stream": 0,
			"request_timeout_seconds": 10, "prompt_bundle_version": "v4", "max_history_length": 40,
		})
		self.cfg.update(settings)
		return srv

	def session(self, owner=None):
		frappe.set_user(owner or self.owner)
		name = frappe.get_doc({"doctype": "AI Chat Session", "title": "New chat", "user": owner or self.owner, "status": "Active"}).insert(ignore_permissions=True).name
		frappe.set_user("Administrator")
		self.sessions.append(name)
		return name

	def send(self, session, message, user=None, **kw):
		frappe.set_user(user or self.owner)
		try:
			return chat.send(session=session, message=message, **kw)
		finally:
			frappe.set_user("Administrator")

	def streamed_text(self, session):
		return "".join(m["chunk"] for ev, m in self.events if ev == "chat_ai:stream" and m.get("session") == session)

	def messages(self, session):
		return frappe.get_all("AI Chat Message", filters={"session": session}, fields=["role", "content", "model", "tokens_in", "tokens_out", "error", "attachments"], order_by="creation, role desc")


def last_user_content(body):
	return body["messages"][-1]["content"]


# ---------------------------------------------------------------------------------------------------
class TestSimpleTurn(FlowCase):
	def test_streamed_answer_is_persisted_once_with_usage(self):
		srv = self.provider(plan(simple=True), stream("Hello", " there,", " friend."))
		s = self.session()
		res = self.send(s, "Say hello to me please")
		self.assertTrue(res["ok"], res)
		self.assertEqual(res["data"]["content"], "Hello there, friend.")
		# provider traffic: planner (JSON, not streamed) then the streamed answer
		planner, answer = srv.requests
		self.assertNotIn("stream", planner["body"])
		self.assertTrue(answer["body"]["stream"])
		self.assertEqual(answer["body"]["model"], "m-main")
		self.assertEqual(answer["body"]["messages"][0]["role"], "system")
		self.assertIn("Say hello to me please", last_user_content(answer["body"]))
		self.assertEqual({k.lower(): v for k, v in answer["headers"].items()}["authorization"], "Bearer test-key")
		# realtime: real deltas, then done exactly once
		self.assertEqual(self.streamed_text(s), "Hello there, friend.")
		done = [m for ev, m in self.events if ev == "chat_ai:stream" and m.get("done")]
		self.assertEqual(len(done), 1)
		# DB: one user + one assistant message, no duplicates
		msgs = self.messages(s)
		self.assertEqual([(m.role, m.content) for m in msgs], [("user", "Say hello to me please"), ("assistant", "Hello there, friend.")])
		self.assertEqual((msgs[1].tokens_in, msgs[1].tokens_out), (16, 11))  # planner 5/7 + answer 11/4
		self.assertEqual(msgs[1].model, "m")
		sess = frappe.get_doc("AI Chat Session", s)
		self.assertTrue(sess.last_message_at)
		self.assertEqual(sess.title, "Say hello to me please")
		usage = frappe.db.get_value("AI Usage Daily", {"user": self.owner, "usage_date": frappe.utils.today(), "model": "m-main"}, ["request_count", "tokens_in", "tokens_out"], as_dict=True)
		self.assertGreaterEqual(usage.request_count, 1)

	def test_history_endpoint_returns_the_persisted_exchange(self):
		self.provider(plan(), stream("Pong."))
		s = self.session()
		self.send(s, "ping")
		frappe.set_user(self.owner)
		rows = chat.history(session=s)["data"]
		self.assertEqual([r["role"] for r in rows], ["user", "assistant"])
		self.assertEqual(rows[1]["content"], "Pong.")

	def test_second_turn_carries_the_conversation(self):
		srv = self.provider(plan(), stream("Your name is Dana."), plan(), stream("Dana, yes."))
		s = self.session()
		self.send(s, "My name is Dana")
		self.send(s, "What is my name?")
		second = srv.requests[3]["body"]["messages"]
		flat = json.dumps(second)
		self.assertIn("My name is Dana", flat)
		self.assertIn("Your name is Dana.", flat)


class TestToolLoop(FlowCase):
	def test_calculator_round_trip(self):
		srv = self.provider(
			plan(simple=False, tools=["calculator"], skills=["workspace"]),
			stream_tool_call("calculator", {"expression": "12*(3+4)"}, preface="Let me compute that. "),
			stream("The answer is 84."),
		)
		s = self.session()
		self.db_settings["enable_audit_logs"] = 1
		res = self.send(s, "What is 12 times (3 plus 4)? Use the calculator.")
		self.assertTrue(res["ok"], res)
		self.assertEqual(res["data"]["content"], "The answer is 84.")
		self.assertEqual(len(srv.requests), 3)  # planner, tool round, final round: the tool ran exactly once
		offered = [t["function"]["name"] for t in srv.requests[1]["body"]["tools"]]
		self.assertIn("calculator", offered)
		self.assertNotIn("web_search", offered)  # disabled by settings
		self.assertNotIn("file_search", offered)  # no files in this conversation
		tool_msg = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "tool"][0]
		self.assertEqual(tool_msg["tool_call_id"], "call_1")
		self.assertEqual(json.loads(tool_msg["content"])["data"]["value"], 84)
		assistant_call = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "assistant"][-1]
		self.assertEqual(json.loads(assistant_call["tool_calls"][0]["function"]["arguments"]), {"expression": "12*(3+4)"})
		# narration before the tool call was shown, then reset so the final answer starts clean
		stream_events = [m for ev, m in self.events if ev == "chat_ai:stream"]
		self.assertTrue(any(m.get("reset") for m in stream_events))
		after_reset = "".join(m["chunk"] for m in stream_events[[i for i, m in enumerate(stream_events) if m.get("reset")][-1] + 1:])
		self.assertEqual(after_reset, "The answer is 84.")
		# audit log written, arguments stored without secrets
		log = frappe.get_all("AI Tool Log", filters={"session": s}, fields=["tool_name", "success", "permission_ok"])
		self.assertEqual([(l.tool_name, l.success) for l in log], [("calculator", 1)])
		self.assertEqual(len([m for m in self.messages(s) if m.role == "assistant"]), 1)

	def test_tool_failure_is_reported_to_the_model_not_raised(self):
		srv = self.provider(
			plan(simple=False, tools=["calculator"], skills=["workspace"]),
			stream_tool_call("calculator", {"expression": "__import__('os').system('id')"}),
			stream("I could not evaluate that."),
		)
		s = self.session()
		res = self.send(s, "compute something nasty")
		self.assertTrue(res["ok"], res)
		tool_msg = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "tool"][0]
		payload = json.loads(tool_msg["content"])
		self.assertFalse(payload["ok"])
		self.assertNotIn("Traceback", tool_msg["content"])

	def test_an_unknown_tool_name_is_not_executed(self):
		srv = self.provider(
			plan(simple=False, tools=["calculator"], skills=["workspace"]),
			stream_tool_call("drop_all_tables", {"x": 1}),
			stream("Sorry, that is not possible."),
		)
		s = self.session()
		res = self.send(s, "do the thing")
		self.assertTrue(res["ok"], res)
		tool_msg = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "tool"][0]
		self.assertFalse(json.loads(tool_msg["content"])["ok"])


class TestWebSearch(FlowCase):
	BRAVE = json.dumps({"web": {"results": [
		{"title": "ZATCA Phase 2", "url": "https://zatca.gov.sa/en/phase2", "description": "Integration phase rules"},
	]}}).encode()

	def _web_cfg(self, **kw):
		return {"local_only": 0, "enable_web_search": 1, "web_search_provider": "Brave", "web_search_api_key": "brave-test", "web_search_max_results": 3, **kw}

	def test_search_answer_carries_only_returned_sources(self):
		brave = ScriptedServer([(200, JSON, self.BRAVE)])
		self.servers.append(brave)
		srv = self.provider(
			plan(simple=False, tools=["web_search"], skills=["workspace"]),
			stream_tool_call("web_search", {"query": "zatca phase 2 deadline"}),
			stream("Phase 2 is the integration phase [1]."),
			**self._web_cfg(),
		)
		s = self.session()
		with mock.patch("zatgo_core.chat_ai.core.web_search.BRAVE_URL", brave.url + "/res/v1/web/search"):
			res = self.send(s, "What is ZATCA phase 2? Search the web.")
		self.assertTrue(res["ok"], res)
		self.assertIn("web_search", [t["function"]["name"] for t in srv.requests[1]["body"]["tools"]])
		sources = res["data"]["sources"]
		self.assertEqual([(x["type"], x["url"], x["domain"], x["title"]) for x in sources],
						 [("web", "https://zatca.gov.sa/en/phase2", "zatca.gov.sa", "ZATCA Phase 2")])
		self.assertEqual(res["data"]["content_json"]["sources"], sources)
		tool_msg = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "tool"][0]
		self.assertEqual(json.loads(tool_msg["content"])["data"]["results"][0]["ref"], 1)
		self.assertIn("X-Subscription-Token", {k.title() if k.lower() != "x-subscription-token" else "X-Subscription-Token": v for k, v in brave.requests[0]["headers"].items()})
		persisted = json.loads(frappe.get_all("AI Chat Message", filters={"session": s, "role": "assistant"}, fields=["content_json"])[0].content_json)
		self.assertEqual(persisted["sources"], sources)

	def test_no_search_no_sources(self):
		self.provider(plan(), stream("Plain answer."), **self._web_cfg())
		s = self.session()
		res = self.send(s, "What is 2+2 in words?")
		self.assertEqual(res["data"]["sources"], [])

	def test_web_tools_are_hidden_when_switched_off_or_unkeyed_or_toggled_off(self):
		for cfg, kwargs in (
			({"enable_web_search": 0, "web_search_provider": "Brave", "web_search_api_key": "k"}, {}),
			({"enable_web_search": 1, "web_search_provider": "Brave", "web_search_api_key": ""}, {}),
			({"enable_web_search": 1, "web_search_provider": "SearXNG", "web_search_url": ""}, {}),
			({"enable_web_search": 1, "web_search_provider": "Brave", "web_search_api_key": "k"}, {"web": 0}),
		):
			srv = self.provider(plan(simple=False, tools=["calculator"], skills=["workspace"]), stream("done"), **cfg)
			self.send(self.session(), "hello there my friend, please do something", **kwargs)
			offered = [t["function"]["name"] for t in srv.requests[1]["body"].get("tools", [])]
			self.assertNotIn("web_search", offered, (cfg, kwargs))
			self.assertNotIn("fetch_url", offered, (cfg, kwargs))

	def test_forced_web_without_a_key_is_a_clear_configuration_message(self):
		srv = self.provider(plan(), stream("never"), enable_web_search=1, web_search_provider="SearXNG", web_search_url="")
		res = self.send(self.session(), "search the web for ZATCA", web=1)
		self.assertTrue(res["ok"])
		self.assertIn("not configured", res["data"]["content"])
		self.assertEqual(srv.requests, [])  # nothing was sent to the model, nothing invented

	def test_failed_search_does_not_fabricate_sources(self):
		brave = ScriptedServer([(500, JSON, b"{}")])
		self.servers.append(brave)
		srv = self.provider(
			plan(simple=False, tools=["web_search"], skills=["workspace"]),
			stream_tool_call("web_search", {"query": "anything"}),
			stream("I could not reach the search service."),
			**self._web_cfg(),
		)
		with mock.patch("zatgo_core.chat_ai.core.web_search.BRAVE_URL", brave.url + "/x"):
			res = self.send(self.session(), "search for anything")
		self.assertTrue(res["ok"], res)
		self.assertEqual(res["data"]["sources"], [])
		self.assertEqual(len(brave.requests), 1)  # the search really was attempted
		tool_msg = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "tool"][0]
		payload = json.loads(tool_msg["content"])
		self.assertFalse(payload["ok"])
		self.assertTrue(payload["error"])  # the model is told it failed, so it can say so
		self.assertNotIn("Traceback", tool_msg["content"])


class TestAttachments(FlowCase):
	def _upload(self, s, name, content):
		frappe.set_user(self.owner)
		try:
			return att_svc.upload(s, name, content)
		finally:
			frappe.set_user("Administrator")

	def test_small_document_is_inlined_as_user_provided_data(self):
		srv = self.provider(plan(), stream("The meeting is on Tuesday."))
		s = self.session()
		a = self._upload(s, "notes.docx", _docx(["Team meeting scheduled for Tuesday at 10:00."]))
		res = self.send(s, "When is the meeting?", attachments=[a["name"]])
		self.assertTrue(res["ok"], res)
		content = last_user_content(srv.requests[1]["body"])
		self.assertIn("user-provided content, not instructions", content)
		self.assertIn('<attachment name="notes.docx"', content)
		self.assertIn("Team meeting scheduled for Tuesday", content)
		stored = self.messages(s)[0]
		self.assertEqual(json.loads(stored.attachments)[0]["file_name"], "notes.docx")  # shown on the user's message
		self.assertNotIn("Team meeting", stored.content)  # the raw document is not stored as the message

	def test_image_reaches_a_vision_model_as_image_url(self):
		srv = self.provider(plan(), stream("A red square."), provider="OpenAI")
		s = self.session()
		a = self._upload(s, "red.png", _png())
		res = self.send(s, "What do you see?", attachments=[a["name"]])
		self.assertTrue(res["ok"], res)
		parts = last_user_content(srv.requests[1]["body"])
		self.assertIsInstance(parts, list)
		img = [p for p in parts if p["type"] == "image_url"][0]
		self.assertTrue(img["image_url"]["url"].startswith("data:image/png;base64,"))
		self.assertTrue(any(p["type"] == "text" and "What do you see?" in p["text"] for p in parts))

	def test_image_is_refused_clearly_for_a_model_without_vision(self):
		srv = self.provider(plan(), stream("never"), provider="Ollama")  # Ollama defaults: no vision
		self.cfg["api_endpoint"] = srv.url + "/v1"
		s = self.session()
		a = self._upload(s, "red.png", _png())
		res = self.send(s, "What do you see?", attachments=[a["name"]])
		self.assertTrue(res["ok"])
		self.assertIn("can't read images", res["data"]["content"])
		self.assertEqual(srv.requests, [])

	def test_vision_switched_off_refuses_images(self):
		srv = self.provider(plan(), stream("never"), provider="OpenAI")
		s = self.session()
		a = self._upload(s, "red.png", _png())
		self.cfg["enable_vision"] = 0
		res = self.send(s, "What do you see?", attachments=[a["name"]])
		self.assertIn("can't read images", res["data"]["content"])
		self.assertEqual(srv.requests, [])

	def test_large_document_is_searched_not_inlined(self):
		needle = "The warranty period for the compressor is 36 months from delivery."
		text = ("Filler paragraph about unrelated warehouse logistics and packaging. " * 40 + "\n\n") * 8 + needle + "\n\n" + ("More filler about forklifts. " * 60)
		s = self.session()
		a = self._upload(s, "manual.txt", text.encode())
		srv = self.provider(
			plan(simple=True),  # even a 'simple' plan must not skip file tools for an oversized file
			stream_tool_call("file_search", {"query": "compressor warranty period months"}),
			stream("The warranty is 36 months [1]."),
		)
		res = self.send(s, "How long is the compressor warranty?", attachments=[a["name"]])
		self.assertTrue(res["ok"], res)
		first = srv.requests[1]["body"]
		self.assertIn("too large to include: manual.txt", last_user_content(first))
		self.assertNotIn(needle, last_user_content(first))
		self.assertIn("file_search", [t["function"]["name"] for t in first["tools"]])
		tool_msg = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "tool"][0]
		self.assertIn("36 months", tool_msg["content"])
		sources = res["data"]["sources"]
		self.assertTrue(sources)
		self.assertTrue(all((x["type"], x["title"]) == ("file", "manual.txt") for x in sources))  # distinct passages of one file
		self.assertTrue(any("36 months" in x["snippet"] for x in sources))

	def test_follow_up_turn_can_search_files_from_an_earlier_message(self):
		needle = "Registration number is CR-4455-ZZ."
		s = self.session()
		a = self._upload(s, "facts.txt", (("Filler line. " * 100 + "\n\n") * 5 + needle + "\n\n" + "Tail filler. " * 400).encode())
		srv = self.provider(
			plan(simple=False), stream_tool_call("file_search", {"query": "registration number"}), stream("It is CR-4455-ZZ."),
		)
		res = self.send(s, "What is the registration number in the file I uploaded earlier?")  # no attachments param
		self.assertTrue(res["ok"], res)
		self.assertIn("file_search", [t["function"]["name"] for t in srv.requests[1]["body"]["tools"]])
		self.assertIn("Earlier files in this conversation", last_user_content(srv.requests[1]["body"]))
		tool_msg = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "tool"][0]
		self.assertIn("CR-4455-ZZ", tool_msg["content"])

	def test_spreadsheet_numbers_come_from_the_analysis_tool(self):
		csv = b"region,amount\nNorth,100\nSouth,\"1,250.50\"\nNorth,49.5\n"
		s = self.session()
		a = self._upload(s, "sales.csv", csv)
		srv = self.provider(
			plan(simple=False, tools=["analyze_table"], skills=["workspace"]),
			stream_tool_call("analyze_table", {"attachment_id": a["name"], "operation": "aggregate", "column": "amount", "func": "sum", "group_by": "region"}),
			stream("North total 149.5, South 1,250.50."),
		)
		res = self.send(s, "Total amount per region?", attachments=[a["name"]])
		self.assertTrue(res["ok"], res)
		tool_msg = [m for m in srv.requests[2]["body"]["messages"] if m["role"] == "tool"][0]
		data = json.loads(tool_msg["content"])["data"]
		self.assertEqual(data["results"], [{"region": "South", "sum": 1250.5}, {"region": "North", "sum": 149.5}])

	def test_someone_elses_attachment_cannot_be_used(self):
		s_owner = self.session()
		a = self._upload(s_owner, "secret.docx", _docx(["Top secret."]))
		s_other = self.session(self.other)
		srv = self.provider(plan(), stream("never"))
		frappe.set_user(self.other)
		res = chat.send(session=s_other, message="read it", attachments=[a["name"]])
		self.assertEqual((res["ok"], res["code"]), (False, "forbidden"))  # not the owner's session
		with self.assertRaises(frappe.PermissionError):
			chat.send(session=s_owner, message="read it")
		frappe.set_user("Administrator")
		self.assertEqual(srv.requests, [])


class TestProviderFailures(FlowCase):
	def test_errors_are_safe_and_classified(self):
		for status, code, retryable in ((401, "auth", False), (404, "model_unavailable", False), (429, "rate_limited", True), (500, "provider_unavailable", True)):
			srv = self.provider(error(status))
			s = self.session()
			res = self.send(s, "hello there")
			self.assertFalse(res["ok"], status)
			self.assertEqual((res["code"], res["retryable"]), (code, retryable), status)
			blob = json.dumps(res)
			for leak in ("UPSTREAM-SECRET-DETAIL", "sk-leak", "Traceback", "127.0.0.1", "test-key"):
				self.assertNotIn(leak, blob, (status, leak))
			self.assertEqual(self.messages(s), [])  # nothing half-saved

	def test_connection_refused(self):
		self.provider()
		self.cfg["api_endpoint"] = "http://127.0.0.1:9/v1"
		res = self.send(self.session(), "hello there")
		self.assertFalse(res["ok"])
		self.assertEqual((res["code"], res["retryable"]), ("network", True))

	def test_stream_that_dies_midway_keeps_the_partial_answer_without_retrying(self):
		srv = self.provider(plan(), stream("The first half of the answer is here, ", "and then", finish=False))
		s = self.session()
		res = self.send(s, "tell me a long story please")
		self.assertTrue(res["ok"], res)
		self.assertIn("The first half of the answer is here", res["data"]["content"])
		self.assertIn("interrupted", res["data"]["content"])
		self.assertEqual(len(srv.requests), 2)  # planner + one stream: no silent retry
		msgs = self.messages(s)
		self.assertEqual([m.role for m in msgs], ["user", "assistant"])  # still exactly one of each
		self.assertEqual(msgs[1].error, "1")

	def test_unexpected_exception_is_generic(self):
		self.provider(plan(), stream("x"))
		with mock.patch.object(orchestrator, "_direct_answer", side_effect=RuntimeError("db password is hunter2")):
			res = self.send(self.session(), "hello there")
		self.assertFalse(res["ok"])
		self.assertEqual(res["code"], "internal")
		self.assertNotIn("hunter2", json.dumps(res))


class TestModelSelection(FlowCase):
	CFG = dict(enable_model_routing=1, model_fast="m-fast", model_coding="m-code", model_vision="m-vision",
			   model_reasoning="m-think", fallback_model="m-backup")

	def models(self, srv):
		return [r["body"]["model"] for r in srv.requests]

	def test_routing_picks_the_slot_and_uses_the_fast_model_to_plan(self):
		cases = (
			("def add(a, b): return a - b  -- why does this fail?", "m-code"),
			("Please analyze the trade-offs between renting and buying a warehouse for our expansion plans in detail", "m-think"),
			("hi there", "m-fast"),
		)
		for text, expected in cases:
			srv = self.provider(plan(), stream("ok"), **self.CFG)
			res = self.send(self.session(), text)
			self.assertTrue(res["ok"], res)
			self.assertEqual(self.models(srv), ["m-fast", expected], text)  # planner on the fast model, answer on the routed one
			self.assertEqual(res["data"]["meta"]["model"], "m")

	def test_vision_slot_for_images(self):
		s = self.session()
		frappe.set_user(self.owner)
		self.provider(plan(), stream("ok"), **self.CFG)
		a = att_svc.upload(s, "red.png", _png())
		frappe.set_user("Administrator")
		srv = self.provider(plan(), stream("A red square."), provider="OpenAI", **self.CFG)
		res = self.send(s, "Describe this picture in detail please, what colours do you see?", attachments=[a["name"]])
		self.assertTrue(res["ok"], res)
		self.assertEqual(self.models(srv)[-1], "m-vision")

	def test_manual_choice_overrides_routing_and_unknown_models_are_rejected(self):
		srv = self.provider(plan(), stream("ok"), **self.CFG)
		res = self.send(self.session(), "hi there", model="m-think")
		self.assertTrue(res["ok"], res)
		self.assertEqual(self.models(srv), ["m-think", "m-think"])  # no rerouting, planner included
		bad = self.send(self.session(), "hi there", model="gpt-not-configured")
		self.assertFalse(bad["ok"])
		self.assertEqual(bad["code"], "invalid")
		self.assertEqual(len(srv.requests), 2)  # the rejected request never reached the provider

	def test_routing_off_always_uses_the_default_model(self):
		srv = self.provider(plan(), stream("ok"), **{**self.CFG, "enable_model_routing": 0})
		self.send(self.session(), "def f(): pass  # why?")
		self.assertEqual(self.models(srv), ["m-main", "m-main"])

	def test_fallback_is_used_and_announced_when_the_user_did_not_choose(self):
		srv = self.provider(plan(), error(503), stream("Answer from the backup."), **{**self.CFG, "enable_model_routing": 0})
		s = self.session()
		res = self.send(s, "please tell me something useful")
		self.assertTrue(res["ok"], res)
		self.assertEqual(res["data"]["content"], "Answer from the backup.")
		self.assertEqual(self.models(srv), ["m-main", "m-main", "m-backup"])
		self.assertEqual(res["data"]["meta"]["fallback_from"], "m-main")
		self.assertEqual(self.messages(s)[1].content, "Answer from the backup.")

	def test_no_silent_fallback_when_the_user_picked_the_model(self):
		srv = self.provider(plan(), error(503), stream("never"), **{**self.CFG, "enable_model_routing": 0})
		res = self.send(self.session(), "please tell me something useful", model="m-think")
		self.assertFalse(res["ok"])
		self.assertEqual((res["code"], res["retryable"]), ("provider_unavailable", True))
		self.assertNotIn("m-backup", self.models(srv))

	def test_no_fallback_for_authentication_errors(self):
		srv = self.provider(plan(), error(401), stream("never"), **{**self.CFG, "enable_model_routing": 0})
		res = self.send(self.session(), "please tell me something useful")
		self.assertEqual(res["code"], "auth")
		self.assertNotIn("m-backup", self.models(srv))


class TestStopAndQuota(FlowCase):
	def test_cancel_set_by_another_request_is_seen_by_a_running_turn(self):
		"""Stop arrives as a separate request: it writes the flag to Redis, not into this
		request's frappe.local cache. A check that memoised an earlier miss would never see it."""
		import pickle

		from zatgo_core.chat_ai.core.tool_pipeline import cancel_key, clear_cancel, is_cancelled

		session = "stop-visibility-test"
		clear_cancel(session)
		self.assertFalse(is_cancelled(session))  # an early check (a miss) must not be remembered
		raw = frappe.cache.make_key(cancel_key(session))
		frappe.cache.set(raw, pickle.dumps(1))  # what the cancel endpoint's request does, bypassing our local cache
		self.addCleanup(lambda: frappe.cache.delete(raw))
		self.assertTrue(is_cancelled(session))


	def test_stop_during_streaming_keeps_the_partial_text(self):
		s = self.session()
		srv = self.provider(plan(), stream("Part one of the answer, ", "part two, ", "part three, ", "part four.", finish=True))

		def stop_after_first_chunk(ev, msg=None, **kw):
			self.events.append((ev, msg or {}))
			if ev == "chat_ai:stream" and msg and msg.get("chunk"):
				request_cancel(s)

		with mock.patch.object(frappe, "publish_realtime", side_effect=stop_after_first_chunk):
			res = self.send(s, "tell me a long answer please")
		self.assertTrue(res["ok"], res)
		self.assertIn("(stopped)", res["data"]["content"])
		self.assertTrue(res["data"]["content"].startswith("Part one"))
		self.assertNotIn("part four", res["data"]["content"])
		# the next turn is not poisoned by the old cancel flag
		self.provider(plan(), stream("Fresh answer."))
		again = self.send(s, "and now?")
		self.assertEqual(again["data"]["content"], "Fresh answer.")

	def test_burst_limit_blocks_before_the_provider_is_called(self):
		srv = self.provider(plan(), stream("one"), plan(), stream("two"))
		user = self.fresh_user("burst")
		s = self.session(user)
		self.db_settings["max_messages_per_minute"] = 1
		first = self.send(s, "first message please", user=user)
		second = self.send(s, "second message please", user=user)
		self.assertTrue(first["ok"], first)
		self.assertFalse(second["ok"])
		self.assertEqual((second["code"], second["retryable"]), ("rate_limited", True))
		self.assertEqual(len(srv.requests), 2)  # only the first turn (planner + answer)

	def test_daily_message_cap_and_token_cap(self):
		for field, value in (("max_messages_per_user_per_day", 1), ("max_tokens_per_user_per_day", 1)):
			srv = self.provider(plan(), stream("ok"), plan(), stream("ok"))
			user = self.fresh_user("cap_" + field[4:12])
			s = self.session(user)
			self.db_settings.clear()
			self.db_settings.update({"max_messages_per_minute": 0, field: value})
			self.assertTrue(self.send(s, "first message please", user=user)["ok"], field)
			blocked = self.send(s, "second message please", user=user)
			self.assertEqual(blocked["code"], "rate_limited", field)
			self.assertEqual(len(srv.requests), 2, field)


class TestRegenerateAndEdit(FlowCase):
	def test_regenerate_replaces_the_answer_without_duplicating_the_question(self):
		srv = self.provider(plan(), stream("First answer."), plan(), stream("Second answer."))
		s = self.session()
		self.send(s, "Explain VAT briefly")
		frappe.set_user(self.owner)
		res = chat.regenerate(session=s)
		frappe.set_user("Administrator")
		self.assertTrue(res["ok"], res)
		self.assertEqual([(m.role, m.content) for m in self.messages(s)], [("user", "Explain VAT briefly"), ("assistant", "Second answer.")])
		self.assertEqual(len(srv.requests), 4)

	def test_edit_discards_later_messages_and_answers_the_new_text(self):
		self.provider(plan(), stream("A1."), plan(), stream("A2."), plan(), stream("A3 for the edited question."))
		s = self.session()
		self.send(s, "question one")
		self.send(s, "question two")
		first_user = [m for m in frappe.get_all("AI Chat Message", filters={"session": s, "role": "user"}, fields=["name"], order_by="creation")][0].name
		frappe.set_user(self.owner)
		res = chat.edit_message(session=s, message=first_user, content="question one, edited")
		frappe.set_user("Administrator")
		self.assertTrue(res["ok"], res)
		self.assertEqual([(m.role, m.content) for m in self.messages(s)], [("user", "question one, edited"), ("assistant", "A3 for the edited question.")])


class TestContextManagement(FlowCase):
	def _seed(self, session, n, owner=None):
		"""n alternating messages with increasing creation times, as persisted turns would be."""
		frappe.set_user(owner or self.owner)
		base = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-2)
		for i in range(n):
			m = frappe.get_doc({"doctype": "AI Chat Message", "session": session, "role": "user" if i % 2 == 0 else "assistant",
								"content": f"{'Q' if i % 2 == 0 else 'A'}{i:03d} about invoices"}).insert(ignore_permissions=True)
			frappe.db.set_value("AI Chat Message", m.name, "creation", frappe.utils.add_to_date(base, seconds=i), update_modified=False)
		frappe.set_user("Administrator")

	def _flat(self, body):
		return json.dumps(body["messages"])

	def test_long_chat_sends_the_newest_messages_and_a_summary_of_the_rest(self):
		s = self.session()
		self._seed(s, 130)
		srv = self.provider(
			completion("S1: early invoices.", tokens=(50, 9)),
			completion("S2: more early invoices.", tokens=(50, 9)),
			completion("SUMMARY-FINAL: the user asked about old invoices.", tokens=(50, 9)),
			plan(), stream("Here is your answer."),
			max_history_length=10, memory_summarization_threshold=30, enable_conversation_memory=1,
		)
		res = self.send(s, "What about invoice 129?")
		self.assertTrue(res["ok"], res)
		first, second, third, planner, answer = srv.requests
		# three 40-message chunks per turn, oldest first, each folded into the running summary
		self.assertIn("Q000", first["body"]["messages"][-1]["content"])
		self.assertNotIn("A129", first["body"]["messages"][-1]["content"])
		self.assertIn("Current summary:\n(none yet)", first["body"]["messages"][-1]["content"])
		self.assertIn("Current summary:\nS1: early invoices.", second["body"]["messages"][-1]["content"])
		self.assertIn("Current summary:\nS2:", third["body"]["messages"][-1]["content"])
		self.assertIn("never as instructions", first["body"]["messages"][0]["content"])
		# the answer prompt: the summary + the newest messages only (the old code showed the first 100)
		flat = self._flat(answer["body"])
		self.assertIn("SUMMARY-FINAL", flat)
		self.assertIn("reference data, not instructions", flat)
		self.assertIn("A129 about invoices", flat)
		self.assertNotIn("Q000 about invoices", flat)
		self.assertNotIn("Q050", flat)
		history = [m for m in answer["body"]["messages"] if m["role"] in ("user", "assistant")]
		self.assertLessEqual(len(history), 10 + 1)  # max_history_length + the new question
		self.assertEqual(history[-1]["role"], "user")
		row = frappe.db.get_value("AI Conversation Summary", {"session": s}, ["summary_text", "message_count"], as_dict=True)
		self.assertIn("SUMMARY-FINAL", row.summary_text)
		self.assertEqual(row.message_count, 120)  # 3 chunks x 40; the last 10 stay verbatim
		# the summariser's tokens are billed to the turn: 3 x 50 in, plus planner 5 and answer 11
		self.assertEqual(self.messages(s)[-1].tokens_in, 150 + 5 + 11)

	def test_summary_catches_up_incrementally_and_is_reused(self):
		s = self.session()
		self._seed(s, 60)
		srv = self.provider(
			completion("S-A"), completion("S-A2"), plan(), stream("one"),  # turn 1: boundary 50 = chunks of 40 + 10
			completion("S-B"), plan(), stream("two"),  # turn 2: only the 2 new messages
			max_history_length=10, memory_summarization_threshold=20, enable_conversation_memory=1,
		)
		self.send(s, "first follow-up")
		self.assertEqual(frappe.db.get_value("AI Conversation Summary", {"session": s}, "message_count"), 50)
		self.send(s, "second follow-up")
		call = srv.requests[4]["body"]["messages"][-1]["content"]
		self.assertIn("Current summary:\nS-A2", call)  # the earlier summary is the base
		self.assertNotIn("Q000", call)  # only what was not covered yet
		self.assertIn("S-B", self._flat(srv.requests[6]["body"]))
		self.assertEqual(frappe.db.get_value("AI Conversation Summary", {"session": s}, "message_count"), 52)

	def test_a_failing_summariser_never_breaks_the_turn(self):
		s = self.session()
		self._seed(s, 80)
		srv = self.provider(error(500), plan(), stream("Still answered."),
							max_history_length=10, memory_summarization_threshold=20, enable_conversation_memory=1)
		res = self.send(s, "hello after a long chat")
		self.assertTrue(res["ok"], (res, len(srv.requests)))
		self.assertEqual(res["data"]["content"], "Still answered.")
		self.assertEqual(len(srv.requests), 3)  # the failed summary, then the normal turn
		self.assertNotIn("Summary of the earlier part", self._flat(srv.requests[-1]["body"]))
		self.assertFalse(frappe.db.exists("AI Conversation Summary", {"session": s}))  # nothing half-written

	def test_short_chats_make_no_summary_call_and_ignore_the_threshold_logic(self):
		s = self.session()
		self._seed(s, 6)
		srv = self.provider(plan(), stream("ok"), max_history_length=40, memory_summarization_threshold=30, enable_conversation_memory=1)
		self.assertTrue(self.send(s, "hi again")["ok"])
		self.assertEqual(len(srv.requests), 2)  # planner + answer only
		self.assertFalse(frappe.db.exists("AI Conversation Summary", {"session": s}))

	def test_summaries_can_be_switched_off_with_conversation_memory(self):
		s = self.session()
		self._seed(s, 80)
		srv = self.provider(plan(), stream("ok"), max_history_length=10, enable_conversation_memory=0)
		self.assertTrue(self.send(s, "hello")["ok"])
		self.assertEqual(len(srv.requests), 2)

	def test_token_budget_trims_history_even_under_the_message_cap(self):
		s = self.session()
		frappe.set_user(self.owner)
		for i in range(12):
			frappe.get_doc({"doctype": "AI Chat Message", "session": s, "role": "user" if i % 2 == 0 else "assistant",
							"content": f"B{i:02d} " + "word " * 1500}).insert(ignore_permissions=True)
		frappe.set_user("Administrator")
		srv = self.provider(plan(), stream("ok"), max_history_length=40, context_window_tokens=6000,
							memory_summarization_threshold=99, max_tokens=500)
		self.assertTrue(self.send(s, "and now?")["ok"])
		history = [m for m in srv.requests[-1]["body"]["messages"] if m["role"] in ("user", "assistant")]
		self.assertLess(len(history), 12)  # ~2k tokens per message: the 6k window cannot hold them all
		self.assertIn("B11", json.dumps(history))  # but the newest is there

	def test_regenerate_does_not_send_the_question_twice(self):
		srv = self.provider(plan(), stream("First."), plan(), stream("Second."))
		s = self.session()
		self.send(s, "UNIQUE-QUESTION-TEXT please")
		frappe.set_user(self.owner)
		chat.regenerate(session=s)
		frappe.set_user("Administrator")
		final = srv.requests[-1]["body"]["messages"]
		occurrences = sum(1 for m in final if "UNIQUE-QUESTION-TEXT" in json.dumps(m["content"]))
		self.assertEqual(occurrences, 1)

	def test_reasoning_slot_turns_on_thinking_for_anthropic_requests(self):
		from zatgo_core.chat_ai.core.providers.base import LLMResult
		from zatgo_core.chat_ai.erpnext.orchestrator import _wants_reasoning

		self.assertTrue(_wants_reasoning({"_route_slot": "reasoning"}))
		self.assertFalse(_wants_reasoning({"_route_slot": "fast"}))
		self.assertTrue(_wants_reasoning({"_model_manual": True, "model_reasoning": "m-think", "default_model": "m-think"}))
		self.assertFalse(_wants_reasoning({"_model_manual": True, "model_reasoning": "m-think", "default_model": "m-fast"}))
		self.assertFalse(_wants_reasoning({"_model_manual": True, "model_reasoning": "", "default_model": ""}))
		del LLMResult


class TestBackgroundTurns(FlowCase):
	def test_a_backgrounded_turn_keeps_attachments_model_and_web_choice(self):
		"""The re-enqueued job must carry everything the user chose, or the worker answers a
		different question (no files, default model, web search ignored)."""
		self.provider(plan(), stream("never"), enable_background_turns=1, model_fast="m-fast")
		s = self.session()
		with mock.patch.object(orchestrator, "enqueue_turn") as enqueue:
			res = self.send(s, "a very heavy question", execution_mode="background", attachments=["ATT1"], model="m-fast", web=1)
		self.assertTrue(res["ok"], res)
		self.assertTrue(res["data"]["queued"])
		kw = enqueue.call_args.kwargs
		self.assertEqual((kw["session_name"], kw["user_message"], kw["execution_mode"]), (s, "a very heavy question", "_worker"))
		self.assertEqual((kw["attachments"], kw["model"], kw["web"], kw["regenerate"]), (["ATT1"], "m-fast", True, False))

	def test_background_worker_does_not_requeue_itself(self):
		srv = self.provider(plan(), stream("Done in the worker."), enable_background_turns=1)
		s = self.session()
		with mock.patch.object(orchestrator, "enqueue_turn") as enqueue:
			frappe.set_user(self.owner)
			data = orchestrator.run_turn(session_name=s, user_message="hello there", execution_mode="_worker")
			frappe.set_user("Administrator")
		enqueue.assert_not_called()
		self.assertEqual(data["content"], "Done in the worker.")


class TestAuthorizationInFlow(FlowCase):
	def test_another_user_cannot_drive_a_session_and_the_provider_is_never_called(self):
		srv = self.provider(plan(), stream("never"))
		s = self.session()
		frappe.set_user(self.other)
		for call in (
			lambda: chat.send(session=s, message="hi"),
			lambda: chat.regenerate(session=s),
			lambda: chat.history(session=s),
			lambda: chat.cancel(session=s),
		):
			with self.assertRaises(frappe.PermissionError):
				call()
		frappe.set_user("Administrator")
		self.assertEqual(srv.requests, [])

	def test_streamed_events_are_addressed_to_the_asking_user_only(self):
		self.provider(plan(), stream("private words"))
		s = self.session()
		calls = []
		with mock.patch.object(frappe, "publish_realtime", side_effect=lambda ev, msg=None, **kw: calls.append((ev, kw))):
			self.send(s, "a private question")
		stream_calls = [kw for ev, kw in calls if ev == "chat_ai:stream"]
		self.assertTrue(stream_calls)
		self.assertTrue(all(kw.get("user") == self.owner for kw in stream_calls))
