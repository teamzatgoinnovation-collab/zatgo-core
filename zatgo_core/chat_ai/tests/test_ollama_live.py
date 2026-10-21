"""ZatGo AI against a REAL Ollama server (skipped when none is reachable).

    ZATGO_OLLAMA_URL=http://zatgo-ollama:11434 ZATGO_OLLAMA_MODEL=llama3.2 ZATGO_OLLAMA_EMBED=nomic-embed-text \\
    bench --site <site> run-tests --app zatgo_core --module zatgo_core.chat_ai.tests.test_ollama_live

Needs the models pulled (`ollama pull llama3.2 && ollama pull nomic-embed-text`). Nothing here talks to an external API.
"""

from __future__ import annotations

import json
import os
import unittest
import urllib.request

from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.chat_ai.core.providers.base import LLMMessage
from zatgo_core.chat_ai.core.providers.registry import ProviderRegistry

URL = os.environ.get("ZATGO_OLLAMA_URL", "http://zatgo-ollama:11434").rstrip("/")
MODEL = os.environ.get("ZATGO_OLLAMA_MODEL", "llama3.2")
EMBED = os.environ.get("ZATGO_OLLAMA_EMBED", "nomic-embed-text")


def _pulled():
	try:
		with urllib.request.urlopen(URL + "/api/tags", timeout=3) as r:
			return [m["name"] for m in json.loads(r.read())["models"]]
	except Exception:
		return None


PULLED = _pulled()


def _has(name):
	return PULLED is not None and any(n == name or n.split(":")[0] == name.split(":")[0] and (":" not in name or n == name) for n in PULLED)


SETTINGS = {
	"provider": "Ollama", "api_endpoint": URL + "/v1", "default_model": MODEL, "embedding_provider": "Ollama",
	"embedding_model": EMBED, "temperature": 0, "max_tokens": 64, "request_timeout_seconds": 280,
}
TOOLS = [{
	"type": "function",
	"function": {
		"name": "get_weather", "description": "Current weather for a city",
		"parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
	},
}]


@unittest.skipUnless(_has(MODEL), f"Ollama with model {MODEL} not reachable at {URL}")
class TestOllamaChat(IntegrationTestCase):
	def test_chat(self):
		p = ProviderRegistry.get_active(SETTINGS)
		r = p.chat([LLMMessage(role="user", content="Reply with the single word: pong")])
		self.assertTrue(r.content.strip())
		self.assertGreater(r.tokens_out, 0)

	def test_ping(self):
		ok, _ms, err = ProviderRegistry.get_active(SETTINGS).ping()
		self.assertTrue(ok, err)

	def test_streaming_events(self):
		p = ProviderRegistry.get_active(SETTINGS)
		events = list(p.chat_events([LLMMessage(role="user", content="Count from one to five in words.")]))
		self.assertEqual(events[-1].kind, "result")
		text = "".join(e.text for e in events if e.kind == "text")
		self.assertTrue(text.strip())
		self.assertEqual(events[-1].result.content.strip(), text.strip())

	def test_tool_call(self):
		p = ProviderRegistry.get_active({**SETTINGS, "max_tokens": 128})
		r = p.chat([LLMMessage(role="user", content="What is the weather in Riyadh? Use the tool.")], tools=TOOLS)
		self.assertTrue(r.tool_calls, f"no tool call; content={r.content!r}")
		fn = r.tool_calls[0]["function"]
		self.assertEqual(fn["name"], "get_weather")
		self.assertIn("riyadh", json.dumps(json.loads(fn["arguments"])).lower())

	def test_tool_call_streamed(self):
		p = ProviderRegistry.get_active({**SETTINGS, "max_tokens": 128})
		events = list(p.chat_events([LLMMessage(role="user", content="What is the weather in Riyadh? Use the tool.")], tools=TOOLS))
		result = events[-1].result
		self.assertTrue(result.tool_calls, f"no streamed tool call; content={result.content!r}")
		self.assertEqual(result.tool_calls[0]["function"]["name"], "get_weather")

	def test_unknown_model_is_a_clean_error(self):
		from zatgo_core.chat_ai.core.providers.errors import ProviderError

		p = ProviderRegistry.get_active({**SETTINGS, "default_model": "no-such-model-xyz"})
		with self.assertRaises(ProviderError) as cm:
			p.chat([LLMMessage(role="user", content="hi")])
		self.assertIn(cm.exception.code, ("model_unavailable", "bad_request", "not_found"))


@unittest.skipUnless(_has(EMBED), f"Ollama with embedding model {EMBED} not reachable at {URL}")
class TestOllamaEmbeddings(IntegrationTestCase):
	def test_embeddings_batch(self):
		p = ProviderRegistry.get_embedding(SETTINGS)
		vecs = p.embed(["annual leave policy", "stock transfer between warehouses"])
		self.assertEqual(len(vecs), 2)
		self.assertTrue(all(len(v) > 100 for v in vecs))
		self.assertNotEqual(vecs[0], vecs[1])
