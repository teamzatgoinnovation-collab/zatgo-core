"""'Local models only' (core/providers/local_guard.py): ZatGo AI talks to Ollama / a server on your own
network and refuses to send anything to an external API. No model is needed: refusals are asserted
before any request is made, and the local paths run against scripted local HTTP servers.

Run: bench --site <site> run-tests --app zatgo_core --module zatgo_core.chat_ai.tests.test_local_only
"""

from __future__ import annotations

import json
import socket
from unittest import mock

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.chat_ai import install, setup_self_hosted
from zatgo_core.chat_ai.core import web_search
from zatgo_core.chat_ai.core.providers import local_guard
from zatgo_core.chat_ai.core.providers.local_guard import ExternalEndpointError
from zatgo_core.chat_ai.core.providers.openai_compat import OpenAICompatProvider
from zatgo_core.chat_ai.core.providers.registry import default_provider, from_settings
from zatgo_core.chat_ai.erpnext import knowledge
from zatgo_core.chat_ai.erpnext.settings import get_settings_dict, local_only_enabled
from zatgo_core.patches.v0_4_4 import chat_ai_local_only_on
from zatgo_core.chat_ai.tests._servers import ScriptedServer

LOCAL = [
	"http://127.0.0.1:11434/v1",
	"http://localhost:11434",
	"http://ollama:11434/v1",
	"http://zatgo-llm:8080",
	"http://10.0.0.5:11434",
	"http://192.168.1.9",
	"http://172.20.0.3:8080/v1",
	"http://host.docker.internal:11434",
	"http://ollama.internal:11434",
	"http://gpu-box.lan:11434",
	"http://[::1]:11434",
	"ollama:11434",  # scheme-less
]
EXTERNAL = [
	"https://api.openai.com/v1",
	"https://api.anthropic.com",
	"https://generativelanguage.googleapis.com/v1beta/openai",
	"https://openrouter.ai/api/v1",
	"https://api.search.brave.com/res/v1/web/search",
	"http://8.8.8.8:11434",
	"ftp://ollama/x",
	"",
	"   ",
]


def _addrinfo(*ips):
	return lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]


class TestLocalGuard(IntegrationTestCase):
	def test_local_urls(self):
		for url in LOCAL:
			self.assertTrue(local_guard.is_local_url(url), url)

	def test_external_urls(self):
		for url in EXTERNAL:
			with mock.patch("socket.getaddrinfo", _addrinfo("104.18.1.1")):
				self.assertFalse(local_guard.is_local_url(url), url)

	def test_dotted_name_is_judged_by_dns(self):
		with mock.patch("socket.getaddrinfo", _addrinfo("10.1.2.3")):
			self.assertTrue(local_guard.is_local_url("https://ollama.corp.example.com"))
		with mock.patch("socket.getaddrinfo", _addrinfo("10.1.2.3", "93.184.216.34")):
			self.assertFalse(local_guard.is_local_url("https://mixed.example.com"))  # one public answer is enough to refuse
		with mock.patch("socket.getaddrinfo", side_effect=OSError("no dns")):
			self.assertFalse(local_guard.is_local_url("https://unresolvable.example.com"))  # can't prove local -> refuse

	def test_switch_is_on_unless_explicitly_off(self):
		for off in (0, "0", False, "false", "no"):
			self.assertFalse(local_guard.is_enabled({"local_only": off}), off)
		for on in (None, "", 1, "1", True):
			self.assertTrue(local_guard.is_enabled({"local_only": on}), on)
		self.assertTrue(local_guard.is_enabled({}))  # a site that was never configured can not leak

	def test_assert_local_message_is_actionable(self):
		with self.assertRaises(ExternalEndpointError) as cm:
			local_guard.assert_local("https://api.openai.com/v1")
		self.assertIn("Ollama", str(cm.exception))
		self.assertIn("Local models only", str(cm.exception))


class TestProviderFactory(IntegrationTestCase):
	def test_default_is_ollama(self):
		self.assertEqual(default_provider({}), "Ollama")
		self.assertEqual(default_provider({"local_only": 0}), "OpenAI")
		p = from_settings({})
		self.assertIsInstance(p, OpenAICompatProvider)
		self.assertEqual((p.name, p.api_endpoint, p.model), ("Ollama", "http://127.0.0.1:11434/v1", "llama3.2"))

	def test_ollama_configured(self):
		p = from_settings({"provider": "Ollama", "api_endpoint": "http://ollama:11434/v1", "default_model": "qwen2.5:3b"})
		self.assertEqual((p.api_endpoint, p.model, p.api_key), ("http://ollama:11434/v1", "qwen2.5:3b", ""))
		self.assertNotIn("Authorization", p._headers())  # Ollama needs no key

	def test_external_providers_refused_before_any_request(self):
		for provider in ("OpenAI", "Anthropic", "Google Gemini", "OpenRouter"):
			with mock.patch("urllib.request.urlopen") as net, self.assertRaises(ExternalEndpointError, msg=provider):
				from_settings({"provider": provider, "api_key": "sk-x"})
			net.assert_not_called()

	def test_external_endpoint_refused_even_with_a_local_label(self):
		for provider in ("Ollama", "Custom OpenAI-compatible"):
			with self.assertRaises(ExternalEndpointError):
				from_settings({"provider": provider, "api_endpoint": "https://api.openai.com/v1"})

	def test_local_server_behind_any_label_is_fine(self):
		p = from_settings({"provider": "OpenAI", "api_endpoint": "http://127.0.0.1:8080/v1", "api_key": "k"})
		self.assertEqual(p.api_endpoint, "http://127.0.0.1:8080/v1")

	def test_embeddings_are_guarded_too(self):
		with self.assertRaises(ExternalEndpointError):
			from_settings(
				{"provider": "Ollama", "embedding_provider": "OpenAI", "embedding_api_key": "k"}, for_embedding=True
			)
		with self.assertRaises(ExternalEndpointError):
			from_settings(
				{"provider": "Ollama", "embedding_provider": "Custom OpenAI-compatible", "embedding_endpoint": "https://api.openai.com/v1"},
				for_embedding=True,
			)
		p = from_settings({"provider": "Ollama", "embedding_provider": "Ollama", "api_endpoint": "http://ollama:11434/v1"}, for_embedding=True)
		self.assertEqual((p.api_endpoint, p.model), ("http://ollama:11434/v1", "nomic-embed-text"))

	def test_switch_off_allows_external(self):
		p = from_settings({"provider": "OpenAI", "api_key": "k", "local_only": 0})
		self.assertEqual(p.api_endpoint, "https://api.openai.com/v1")


class TestSettingsValidation(IntegrationTestCase):
	def doc(self, **values):
		doc = frappe.get_doc("Chat AI Settings")
		doc.update({"local_only": 1, "provider": "Ollama", "api_endpoint": "", "embedding_provider": "", "enable_web_search": 0, **values})
		return doc

	def test_ollama_with_defaults_is_valid(self):
		self.doc().validate()
		self.doc(api_endpoint="http://ollama:11434/v1", embedding_provider="Ollama").validate()

	def test_external_provider_is_refused_on_save(self):
		with self.assertRaises(frappe.ValidationError):
			self.doc(provider="OpenAI", api_endpoint="").validate()
		with self.assertRaises(frappe.ValidationError):
			self.doc(provider="Custom OpenAI-compatible", api_endpoint="https://api.openai.com/v1").validate()
		with self.assertRaises(frappe.ValidationError):
			self.doc(embedding_provider="OpenAI", embedding_endpoint="https://api.openai.com/v1").validate()

	def test_brave_and_external_searxng_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.doc(enable_web_search=1, web_search_provider="Brave").validate()
		with mock.patch("socket.getaddrinfo", _addrinfo("104.18.1.1")), self.assertRaises(frappe.ValidationError):
			self.doc(enable_web_search=1, web_search_provider="SearXNG", web_search_url="https://search.example.com").validate()
		self.doc(enable_web_search=1, web_search_provider="SearXNG", web_search_url="http://zatgo-searxng:8080").validate()

	def test_switch_off_or_setup_flag_skips_the_check(self):
		self.doc(local_only=0, provider="OpenAI").validate()
		doc = self.doc(provider="OpenAI")
		doc.flags.ignore_local_only = True  # install/migrate saves must not fail on an old external provider
		doc.validate()

	def test_doctype_defaults(self):
		meta = frappe.get_meta("Chat AI Settings")
		self.assertEqual(meta.get_field("local_only").default, "1")
		self.assertEqual(meta.get_field("provider").default, "Ollama")


class TestKeylessLocalServer(IntegrationTestCase):
	"""An Ollama / llama.cpp server has no API key: nothing may depend on one."""

	def test_embedder_needs_no_key_on_a_local_server(self):
		p = knowledge._embedder(
			{"provider": "Ollama", "embedding_provider": "Ollama", "api_endpoint": "http://ollama:11434/v1"}
		)
		self.assertIsNotNone(p)
		self.assertEqual(p.api_endpoint, "http://ollama:11434/v1")

	def test_embedder_still_off_without_an_embedding_provider(self):
		self.assertIsNone(knowledge._embedder({"provider": "Ollama", "api_endpoint": "http://ollama:11434/v1"}))

	def test_external_embedder_needs_its_key_and_the_switch_off(self):
		cfg = {"provider": "OpenAI", "embedding_provider": "OpenAI", "local_only": 0}
		self.assertIsNone(knowledge._embedder(cfg))  # external and keyless
		self.assertIsNotNone(knowledge._embedder({**cfg, "embedding_api_key": "k"}))
		self.assertIsNone(knowledge._embedder({"provider": "OpenAI", "embedding_provider": "OpenAI", "embedding_api_key": "k"}))  # switch on -> refused


class TestWebSearchLocalOnly(IntegrationTestCase):
	def test_only_a_local_searxng_counts_as_configured(self):
		on = {"enable_web_search": 1}
		self.assertTrue(web_search.is_configured({**on, "web_search_provider": "SearXNG", "web_search_url": "http://zatgo-searxng:8080"}))
		self.assertFalse(web_search.is_configured({**on, "web_search_provider": "Brave", "web_search_api_key": "k"}))
		with mock.patch("socket.getaddrinfo", _addrinfo("104.18.1.1")):
			self.assertFalse(web_search.is_configured({**on, "web_search_provider": "SearXNG", "web_search_url": "https://search.example.com"}))
		self.assertTrue(web_search.is_configured({**on, "local_only": 0, "web_search_provider": "Brave", "web_search_api_key": "k"}))

	def test_get_provider_refuses_brave(self):
		with self.assertRaises(web_search.WebToolError):
			web_search.get_provider({"enable_web_search": 1, "web_search_provider": "Brave", "web_search_api_key": "k"})
		p = web_search.get_provider({"enable_web_search": 1, "web_search_provider": "SearXNG", "web_search_url": "http://zatgo-searxng:8080"})
		self.assertEqual(p.name, "SearXNG")


class TestInstallDoesNotUndoLocalSetup(IntegrationTestCase):
	def fake(self, provider, endpoint, key=""):
		doc = mock.MagicMock()
		doc.provider, doc.api_endpoint = provider, endpoint
		doc.get_password.return_value = key
		doc.as_dict.return_value = {"provider": provider, "api_endpoint": endpoint}
		doc.flags = frappe._dict()
		return doc

	def test_local_endpoint_on_a_custom_provider_survives(self):
		for endpoint in ("http://127.0.0.1:11434/v1", "http://localhost:8080/v1"):
			doc = self.fake("Custom OpenAI-compatible", endpoint)
			with mock.patch("frappe.get_single", return_value=doc):
				install._sanitize_provider_settings()
			self.assertEqual(doc.api_endpoint, endpoint)
			doc.save.assert_not_called()

	def test_openrouter_key_does_not_switch_a_local_site_to_openrouter(self):
		doc = self.fake("Ollama", "http://ollama:11434/v1", key="sk-or-secret")
		with mock.patch("frappe.get_single", return_value=doc), mock.patch(
			"zatgo_core.chat_ai.erpnext.settings.local_only_enabled", return_value=True
		):
			install._sanitize_provider_settings()
		self.assertEqual(doc.provider, "Ollama")
		doc.save.assert_not_called()


class TestOllamaSetup(IntegrationTestCase):
	FIELDS = ("local_only", "provider", "api_endpoint", "default_model", "embedding_provider", "embedding_endpoint",
			  "embedding_model", "context_window_tokens", "enable_web_search", "web_search_provider", "web_search_url",
			  "request_timeout_seconds", "max_tokens", "enable_model_routing")

	def setUp(self):
		frappe.set_user("Administrator")
		# The raw stored rows: get_single_value() can't tell "never saved" from 0 for a checkbox.
		self._before = {
			f: (frappe.db.sql("select value from `tabSingles` where doctype='Chat AI Settings' and field=%s", f) or [[None]])[0][0]
			if frappe.db.sql("select 1 from `tabSingles` where doctype='Chat AI Settings' and field=%s", f)
			else None
			for f in self.FIELDS
		}

	def tearDown(self):
		frappe.set_user("Administrator")
		for f, v in self._before.items():
			if v is None:  # it had no stored value: remove ours (writing None would store an empty one)
				frappe.db.delete("Singles", {"doctype": "Chat AI Settings", "field": f})
			else:
				frappe.db.set_single_value("Chat AI Settings", f, v)
		frappe.db.commit()  # configure_ollama() commits; so must the restore
		frappe.clear_document_cache("Chat AI Settings", "Chat AI Settings")

	def test_configure_ollama_sets_a_local_only_setup(self):
		out = setup_self_hosted.configure_ollama("http://ollama:11434", model="qwen2.5:3b", searxng_url="http://zatgo-searxng:8080")
		s = frappe.get_single("Chat AI Settings")
		self.assertEqual((s.provider, s.api_endpoint, s.default_model), ("Ollama", "http://ollama:11434/v1", "qwen2.5:3b"))
		self.assertEqual((s.embedding_provider, s.embedding_endpoint, s.embedding_model), ("Ollama", "http://ollama:11434/v1", "nomic-embed-text"))
		self.assertEqual(int(s.local_only), 1)
		self.assertEqual(out["context_window_tokens"], 4096)

	def test_configure_ollama_refuses_an_external_url(self):
		with mock.patch("socket.getaddrinfo", _addrinfo("104.18.1.1")), self.assertRaises(frappe.ValidationError):
			setup_self_hosted.configure_ollama("https://ollama.example.com")

	def test_check_reports_pulled_and_missing_models(self):
		setup_self_hosted.configure_ollama("http://127.0.0.1:1", model="llama3.2")
		tags = {"models": [{"name": "llama3.2:latest"}, {"name": "nomic-embed-text:latest"}]}
		srv = ScriptedServer([(200, "application/json", json.dumps(tags).encode())] * 4)
		self.addCleanup(srv.stop)
		frappe.db.set_single_value("Chat AI Settings", "api_endpoint", srv.url + "/v1")
		frappe.db.set_single_value("Chat AI Settings", "embedding_endpoint", srv.url + "/v1")
		frappe.clear_document_cache("Chat AI Settings", "Chat AI Settings")
		out = setup_self_hosted.check()
		self.assertEqual((out["chat"], out["embeddings"], out["local_only"]), ("ok", "ok", True))
		frappe.db.set_single_value("Chat AI Settings", "default_model", "mistral")
		frappe.clear_document_cache("Chat AI Settings", "Chat AI Settings")
		self.assertEqual(setup_self_hosted.check()["chat"], "model not pulled: mistral")

	def test_check_reports_an_unreachable_server(self):
		setup_self_hosted.configure_ollama("http://127.0.0.1:1")
		self.assertEqual(setup_self_hosted.check()["chat"], "unreachable")


class TestExistingSites(IntegrationTestCase):
    """A site that predates the field has no stored value: that must still mean ON, never off.
    (Frappe's doc.as_dict() turns a missing Check into 0 -- the pitfall these tests pin.)"""

    def setUp(self):
        frappe.set_user("Administrator")
        self._row = frappe.db.sql(
            "select value from `tabSingles` where doctype='Chat AI Settings' and field='local_only'"
        )

    def tearDown(self):
        frappe.db.delete("Singles", {"doctype": "Chat AI Settings", "field": "local_only"})
        if self._row:
            frappe.db.set_single_value("Chat AI Settings", "local_only", self._row[0][0])
        frappe.clear_document_cache("Chat AI Settings", "Chat AI Settings")
        frappe.db.commit()

    def _never_saved(self):
        frappe.db.delete("Singles", {"doctype": "Chat AI Settings", "field": "local_only"})
        frappe.clear_document_cache("Chat AI Settings", "Chat AI Settings")

    def test_missing_value_counts_as_on_even_though_as_dict_says_zero(self):
        self._never_saved()
        self.assertEqual(int(frappe.get_single("Chat AI Settings").as_dict()["local_only"] or 0), 0)  # the pitfall
        self.assertTrue(local_only_enabled())
        self.assertEqual(get_settings_dict()["local_only"], 1)

    def test_a_site_without_the_value_refuses_an_external_provider(self):
        self._never_saved()
        with self.assertRaises(ExternalEndpointError):
            from_settings({**get_settings_dict(), "provider": "OpenAI", "api_endpoint": "", "api_key": "sk-x"})

    def test_an_explicit_off_is_respected(self):
        frappe.db.set_single_value("Chat AI Settings", "local_only", 0)
        frappe.clear_document_cache("Chat AI Settings", "Chat AI Settings")
        self.assertFalse(local_only_enabled())
        self.assertEqual(get_settings_dict()["local_only"], 0)
        self.assertEqual(from_settings({**get_settings_dict(), "provider": "OpenAI", "api_endpoint": "", "api_key": "k"}).api_endpoint, "https://api.openai.com/v1")

    def test_an_empty_stored_value_is_not_an_off_switch(self):
        frappe.db.set_single_value("Chat AI Settings", "local_only", None)
        frappe.clear_document_cache("Chat AI Settings", "Chat AI Settings")
        self.assertTrue(local_only_enabled())

    def test_patch_ticks_the_box_where_never_saved_and_leaves_an_explicit_off(self):
        self._never_saved()
        chat_ai_local_only_on.execute()
        self.assertEqual(int(frappe.db.get_single_value("Chat AI Settings", "local_only")), 1)
        frappe.db.set_single_value("Chat AI Settings", "local_only", 0)
        chat_ai_local_only_on.execute()
        self.assertEqual(int(frappe.db.get_single_value("Chat AI Settings", "local_only")), 0)
