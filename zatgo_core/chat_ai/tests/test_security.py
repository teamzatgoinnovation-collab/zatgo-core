"""Owner scoping, confirmation tokens, quotas, usage counters, provider errors.

Run: bench --site <site> run-tests --app zatgo_core --module zatgo_core.chat_ai.tests.test_security
(the module switch is patched on, so the site's ZG System Settings stay untouched)
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.chat_ai import permissions
from zatgo_core.chat_ai.core.providers.base import LLMMessage
from zatgo_core.chat_ai.core.providers.errors import ProviderError, from_http_status
from zatgo_core.chat_ai.core.providers.openai_compat import OpenAICompatProvider
from zatgo_core.chat_ai.core import quota
from zatgo_core.chat_ai.erpnext import confirmation_tokens as tokens


def _user(email: str) -> str:
	if not frappe.db.exists("User", email):
		u = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": "Chat AI User"}],
			}
		)
		u.insert(ignore_permissions=True)
	return email


def _as(user: str):
	frappe.set_user(user)


class TestOwnerScoping(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.patch = mock.patch("zatgo_core.services.bundled_apps.is_on", return_value=True)
		cls.patch.start()
		cls.a = _user("chat_sec_a@example.com")
		cls.b = _user("chat_sec_b@example.com")
		# Created as their owner, like the real send path does (Frappe's own
		# if_owner stamps `owner`); the hooks below do not depend on it.
		frappe.set_user(cls.a)
		cls.session = frappe.get_doc(
			{"doctype": "AI Chat Session", "title": "A secret", "user": cls.a, "status": "Active"}
		).insert(ignore_permissions=True)
		cls.message = frappe.get_doc(
			{"doctype": "AI Chat Message", "session": cls.session.name, "role": "user", "content": "private"}
		).insert(ignore_permissions=True)
		frappe.set_user("Administrator")
		# No if_owner on these doctypes: only our hooks protect them. Inserted by
		# Administrator on purpose, so `owner` can't be what grants access.
		cls.memory = frappe.get_doc(
			{"doctype": "AI Chat Memory", "session": cls.session.name, "user": cls.a, "entities_json": "{}"}
		).insert(ignore_permissions=True)
		cls.summary = frappe.get_doc(
			{"doctype": "AI Conversation Summary", "session": cls.session.name, "summary_text": "s"}
		).insert(ignore_permissions=True)
		cls.toollog = frappe.get_doc(
			{"doctype": "AI Tool Log", "session": cls.session.name, "user": cls.a, "tool_name": "t"}
		).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls.patch.stop()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_owner_sees_own_rows(self):
		_as(self.a)
		self.assertIn(self.session.name, frappe.get_list("AI Chat Session", pluck="name"))
		self.assertIn(self.message.name, frappe.get_list("AI Chat Message", pluck="name"))

	def test_other_user_cannot_list(self):
		_as(self.b)
		self.assertNotIn(self.session.name, frappe.get_list("AI Chat Session", pluck="name"))
		self.assertNotIn(self.message.name, frappe.get_list("AI Chat Message", pluck="name"))

	def test_other_user_cannot_read_by_id(self):
		_as(self.b)
		self.assertFalse(frappe.has_permission("AI Chat Session", "read", doc=self.session.name))
		self.assertFalse(frappe.has_permission("AI Chat Message", "read", doc=self.message.name))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("AI Chat Message", self.message.name).check_permission("read")

	def test_other_user_cannot_delete(self):
		_as(self.b)
		self.assertFalse(frappe.has_permission("AI Chat Session", "delete", doc=self.session.name))

	def test_hooks_protect_doctypes_without_if_owner(self):
		for dt, doc in (
			("AI Chat Memory", self.memory),
			("AI Conversation Summary", self.summary),
			("AI Tool Log", self.toollog),
		):
			_as(self.a)
			self.assertIn(doc.name, frappe.get_list(dt, pluck="name"), dt)
			self.assertTrue(frappe.has_permission(dt, "read", doc=doc.name), dt)
			_as(self.b)
			self.assertNotIn(doc.name, frappe.get_list(dt, pluck="name"), dt)
			self.assertFalse(frappe.has_permission(dt, "read", doc=doc.name), dt)
			frappe.set_user("Administrator")

	def test_users_cannot_write_audit_or_index_doctypes(self):
		for dt in ("AI Tool Log", "AI Usage Daily"):
			perms = [p for p in frappe.get_meta(dt).permissions if p.role == "Chat AI User"]
			self.assertTrue(all(not (p.write or p.create or p.delete) for p in perms), dt)
		for dt in ("AI Search Index", "AI Provider Health Log"):
			self.assertFalse([p for p in frappe.get_meta(dt).permissions if p.role == "Chat AI User"], dt)

	def test_manager_sees_all(self):
		self.assertEqual(permissions.owner_query("AI Chat Session", "Administrator"), "")
		self.assertIn(self.session.name, frappe.get_list("AI Chat Session", pluck="name"))

	def test_session_endpoint_denies_other_user(self):
		from zatgo_core.chat_ai.api import chat

		_as(self.b)
		with self.assertRaises(frappe.PermissionError):
			chat.history(session=self.session.name)
		with self.assertRaises(frappe.PermissionError):
			chat.delete_session(session=self.session.name)
		with self.assertRaises(frappe.PermissionError):
			chat.rename(session=self.session.name, title="pwned")
		self.assertEqual(frappe.db.get_value("AI Chat Session", self.session.name, "title"), "A secret")

	def test_send_denies_other_users_session(self):
		from zatgo_core.chat_ai.api import chat

		_as(self.b)
		with self.assertRaises(frappe.PermissionError):
			chat.send(session=self.session.name, message="hi")


class TestConfirmationTokens(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_token_is_random_and_single_use(self):
		t1 = tokens.issue_token("S1", {"kind": "tool", "tool": "x"})
		t2 = tokens.issue_token("S1", {"kind": "tool", "tool": "x"})
		self.assertNotEqual(t1, t2)
		self.assertGreaterEqual(len(t1), 32)
		self.assertEqual(tokens.consume_token("S1", t1, "tool")["tool"], "x")
		self.assertIsNone(tokens.consume_token("S1", t1, "tool"))

	def test_token_bound_to_session_kind_and_user(self):
		t = tokens.issue_token("S1", {"kind": "tool"})
		self.assertIsNone(tokens.consume_token("S2", t, "tool"))
		self.assertIsNone(tokens.consume_token("S1", t, "plan"))
		frappe.set_user("Guest")
		self.assertIsNone(tokens.consume_token("S1", t, "tool"))
		frappe.set_user("Administrator")
		self.assertIsNotNone(tokens.consume_token("S1", t, "tool"))


class TestQuota(IntegrationTestCase):
	def setUp(self):
		frappe.cache.delete_value("chat_ai_rate:Administrator")

	def tearDown(self):
		frappe.cache.delete_value("chat_ai_rate:Administrator")

	def test_burst_limit(self):
		with mock.patch.object(frappe.db, "get_single_value", return_value=3):
			for _ in range(3):
				quota.enforce("Administrator")
			with self.assertRaises(quota.QuotaExceeded):
				quota.enforce("Administrator")

	def test_burst_limit_zero_disables(self):
		with mock.patch.object(frappe.db, "get_single_value", return_value=0):
			for _ in range(50):
				quota.enforce("Administrator")

	def test_token_caps(self):
		frappe.set_user("Administrator")
		user = _user("chat_tokens@example.com")
		frappe.get_doc(
			{
				"doctype": "AI Usage Daily", "usage_date": frappe.utils.today(), "user": user,
				"provider": "t", "model": "t", "tokens_in": 600, "tokens_out": 500,
			}
		).insert(ignore_permissions=True)
		settings = {"max_tokens_per_user_per_day": 1000, "max_tokens_per_user_per_month": 0}
		with mock.patch.object(frappe.db, "get_single_value", side_effect=lambda dt, f: settings.get(f, 0)):
			with self.assertRaises(quota.QuotaExceeded):
				quota.enforce(user)
		settings = {"max_tokens_per_user_per_day": 0, "max_tokens_per_user_per_month": 1100}
		with mock.patch.object(frappe.db, "get_single_value", side_effect=lambda dt, f: settings.get(f, 0)):
			with self.assertRaises(quota.QuotaExceeded):
				quota.enforce(user)
		settings = {"max_tokens_per_user_per_day": 5000, "max_tokens_per_user_per_month": 5000}
		with mock.patch.object(frappe.db, "get_single_value", side_effect=lambda dt, f: settings.get(f, 0)):
			quota.enforce(user)

	def test_upload_limit(self):
		frappe.cache.delete_value("chat_ai_upload_rate:Administrator")
		for _ in range(2):
			quota.enforce_upload("Administrator", limit=2)
		with self.assertRaises(quota.QuotaExceeded):
			quota.enforce_upload("Administrator", limit=2)
		frappe.cache.delete_value("chat_ai_upload_rate:Administrator")

	def test_daily_cap(self):
		frappe.set_user("Administrator")
		user = _user("chat_quota@example.com")
		frappe.get_doc(
			{
				"doctype": "AI Usage Daily",
				"usage_date": frappe.utils.today(),
				"user": user,
				"provider": "t",
				"model": "t",
				"request_count": 2,
			}
		).insert(ignore_permissions=True)
		with mock.patch.object(frappe.db, "get_single_value", return_value=2):
			with self.assertRaises(quota.QuotaExceeded):
				quota.enforce(user)
		with mock.patch.object(frappe.db, "get_single_value", return_value=0):
			quota.enforce(user)  # 0 = unlimited


class TestUsageCounters(IntegrationTestCase):
	def test_increments_accumulate(self):
		from zatgo_core.chat_ai.erpnext.orchestrator import _record_usage

		frappe.set_user("Administrator")
		settings = {"provider": "usage-test", "default_model": "m-1"}
		_record_usage(settings, (10, 5), 0.5, latency=100)
		_record_usage(settings, (20, 7), 0.25, error=True, latency=300)
		row = frappe.db.get_value(
			"AI Usage Daily",
			{"usage_date": frappe.utils.today(), "user": "Administrator", "provider": "usage-test", "model": "m-1"},
			["tokens_in", "tokens_out", "cost_estimate", "request_count", "error_count", "avg_latency_ms"],
			as_dict=True,
		)
		self.assertEqual((row.tokens_in, row.tokens_out, row.request_count, row.error_count), (30, 12, 2, 1))
		self.assertAlmostEqual(float(row.cost_estimate), 0.75, places=4)
		self.assertAlmostEqual(float(row.avg_latency_ms), 200, delta=1)


class _Handler(BaseHTTPRequestHandler):
	status = 200

	def do_POST(self):
		self.rfile.read(int(self.headers.get("Content-Length") or 0))
		body = json.dumps({"error": {"message": "SECRET-INTERNAL sk-leak"}}).encode()
		self.send_response(type(self).status)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(body)

	def log_message(self, *a):
		pass


class TestProviderErrors(IntegrationTestCase):
	def _provider(self, status):
		handler = type("H", (_Handler,), {"status": status})
		server = HTTPServer(("127.0.0.1", 0), handler)
		threading.Thread(target=server.serve_forever, daemon=True).start()
		self.addCleanup(server.shutdown)
		return OpenAICompatProvider(
			api_key="k", api_endpoint=f"http://127.0.0.1:{server.server_port}/v1", model="m", timeout=5
		)

	def test_http_status_mapping(self):
		self.assertEqual(from_http_status(401).code, "auth")
		self.assertEqual(from_http_status(404).code, "model_unavailable")
		self.assertTrue(from_http_status(429).retryable)
		self.assertTrue(from_http_status(503).retryable)
		self.assertFalse(from_http_status(400).retryable)

	def test_provider_error_hides_upstream_body(self):
		for status, code in ((401, "auth"), (429, "rate_limited"), (500, "provider_unavailable")):
			p = self._provider(status)
			with self.assertRaises(ProviderError) as cm:
				p.chat([LLMMessage(role="user", content="hi")])
			self.assertEqual(cm.exception.code, code)
			self.assertNotIn("SECRET-INTERNAL", cm.exception.message)
			self.assertNotIn("SECRET-INTERNAL", str(cm.exception))
			self.assertIn("SECRET-INTERNAL", cm.exception.detail)

	def test_unreachable_provider(self):
		p = OpenAICompatProvider(api_key="k", api_endpoint="http://127.0.0.1:9/v1", model="m", timeout=2)
		with self.assertRaises(ProviderError) as cm:
			p.chat([LLMMessage(role="user", content="hi")])
		self.assertEqual(cm.exception.code, "network")
