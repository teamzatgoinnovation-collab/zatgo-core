"""Provider adapters and the streaming round, against local HTTP servers.

Run: bench --site <site> run-tests --app zatgo_core --module zatgo_core.chat_ai.tests.test_providers
"""

from __future__ import annotations

import json
from unittest import mock

import frappe
from frappe.tests.classes.integration_test_case import IntegrationTestCase

from zatgo_core.chat_ai.core.providers import anthropic_native
from zatgo_core.chat_ai.core.providers.anthropic_native import AnthropicProvider, normalize_base_url
from zatgo_core.chat_ai.core.providers.base import LLMMessage, LLMResult, StreamEvent
from zatgo_core.chat_ai.core.providers.errors import ProviderError
from zatgo_core.chat_ai.core.providers.openai_compat import OpenAICompatProvider
from zatgo_core.chat_ai.core.providers.registry import ProviderRegistry, from_settings
from zatgo_core.chat_ai.erpnext import streaming
from zatgo_core.chat_ai.tests._servers import ScriptedServer, sse

TOOLS = [
	{
		"type": "function",
		"function": {
			"name": "get_weather",
			"description": "Weather",
			"parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
		},
	}
]


def _compat(server) -> OpenAICompatProvider:
	return OpenAICompatProvider(api_key="k", api_endpoint=server.url + "/v1", model="m", timeout=5)


def _anthropic(server, **kw) -> AnthropicProvider:
	return AnthropicProvider(api_key="k", api_endpoint=server.url, model="claude-test", timeout=5, **kw)


class TestOpenAICompatStreaming(IntegrationTestCase):
	def test_text_and_usage(self):
		srv = ScriptedServer(
			[
				(
					200,
					"text/event-stream",
					sse(
						(None, {"model": "m", "choices": [{"delta": {"content": "Hel"}}]}),
						(None, {"choices": [{"delta": {"content": "lo"}}]}),
						(None, {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2}}),
						(None, "[DONE]"),
					),
				)
			]
		)
		self.addCleanup(srv.stop)
		evs = list(_compat(srv).chat_events([LLMMessage(role="user", content="hi")]))
		self.assertEqual([e.text for e in evs if e.kind == "text"], ["Hel", "lo"])
		res = evs[-1].result
		self.assertEqual((res.content, res.tokens_in, res.tokens_out), ("Hello", 7, 2))
		self.assertTrue(srv.requests[0]["body"]["stream"])

	def test_tool_call_fragments_assembled(self):
		srv = ScriptedServer(
			[
				(
					200,
					"text/event-stream",
					sse(
						(None, {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "get_weather", "arguments": ""}}]}}]}),
						(None, {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"city":'}}]}}]}),
						(None, {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"Riyadh"}'}}]}}]}),
						(None, "[DONE]"),
					),
				)
			]
		)
		self.addCleanup(srv.stop)
		evs = list(_compat(srv).chat_events([LLMMessage(role="user", content="w")], tools=TOOLS))
		call = evs[-1].result.tool_calls[0]
		self.assertEqual(call["id"], "c1")
		self.assertEqual(call["function"]["name"], "get_weather")
		self.assertEqual(json.loads(call["function"]["arguments"]), {"city": "Riyadh"})
		self.assertEqual(srv.requests[0]["body"]["tools"][0]["function"]["name"], "get_weather")

	def test_http_error_is_provider_error(self):
		srv = ScriptedServer([(401, "application/json", b'{"error":"nope"}')])
		self.addCleanup(srv.stop)
		with self.assertRaises(ProviderError) as cm:
			list(_compat(srv).chat_events([LLMMessage(role="user", content="hi")]))
		self.assertEqual(cm.exception.code, "auth")


def _anthropic_stream(text_parts, tool=None, usage=(11, 4)):
	events = [
		("message_start", {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test", "content": [], "stop_reason": None, "usage": {"input_tokens": usage[0], "output_tokens": 0}}}),
		("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
	]
	for t in text_parts:
		events.append(("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}}))
	events.append(("content_block_stop", {"type": "content_block_stop", "index": 0}))
	if tool:
		events += [
			("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "tu_1", "name": tool[0], "input": {}}}),
			("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": tool[1][:6]}}),
			("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": tool[1][6:]}}),
			("content_block_stop", {"type": "content_block_stop", "index": 1}),
		]
	events += [
		("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use" if tool else "end_turn"}, "usage": {"output_tokens": usage[1]}}),
		("message_stop", {"type": "message_stop"}),
	]
	return sse(*events)


class TestAnthropicNative(IntegrationTestCase):
	def setUp(self):
		if not anthropic_native.sdk_available():
			self.skipTest("anthropic SDK not installed")

	def test_normalize_base_url(self):
		self.assertEqual(normalize_base_url("https://api.anthropic.com/v1"), "https://api.anthropic.com")
		self.assertEqual(normalize_base_url(""), "https://api.anthropic.com")
		self.assertEqual(normalize_base_url("http://proxy:9/"), "http://proxy:9")

	def test_streaming_text_tool_use_and_usage(self):
		srv = ScriptedServer([(200, "text/event-stream", _anthropic_stream(["Let ", "me check."], tool=("get_weather", '{"city": "Jeddah"}')))])
		self.addCleanup(srv.stop)
		evs = list(
			_anthropic(srv).chat_events(
				[LLMMessage(role="system", content="Be brief."), LLMMessage(role="user", content="weather?")],
				tools=TOOLS,
			)
		)
		self.assertEqual([e.text for e in evs if e.kind == "text"], ["Let ", "me check."])
		res = evs[-1].result
		self.assertEqual(res.content, "Let me check.")
		self.assertEqual((res.tokens_in, res.tokens_out), (11, 4))
		call = res.tool_calls[0]
		self.assertEqual((call["id"], call["function"]["name"]), ("tu_1", "get_weather"))
		self.assertEqual(json.loads(call["function"]["arguments"]), {"city": "Jeddah"})
		body = srv.requests[0]["body"]
		self.assertTrue(srv.requests[0]["path"].endswith("/v1/messages"))
		self.assertEqual({k.lower(): v for k, v in srv.requests[0]["headers"].items()}.get("x-api-key"), "k")
		self.assertEqual(body["system"][0]["text"], "Be brief.")
		self.assertEqual(body["system"][0]["cache_control"], {"type": "ephemeral"})
		self.assertEqual(body["tools"][0], {"name": "get_weather", "description": "Weather", "input_schema": TOOLS[0]["function"]["parameters"]})

	def test_message_conversion_tool_round_and_image(self):
		srv = ScriptedServer([(200, "application/json", json.dumps({"id": "m", "type": "message", "role": "assistant", "model": "claude-test", "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}}).encode())])
		self.addCleanup(srv.stop)
		png = "data:image/png;base64,iVBORw0KGgo="
		res = _anthropic(srv).chat(
			[
				LLMMessage(role="system", content="S"),
				LLMMessage(role="user", content="look", images=[png]),
				LLMMessage(role="assistant", content="", tool_calls=[{"id": "t1", "type": "function", "function": {"name": "f", "arguments": '{"a": 1}'}}]),
				LLMMessage(role="tool", content='{"ok": true}', tool_call_id="t1", name="f"),
				LLMMessage(role="tool", content='{"ok": 2}', tool_call_id="t2", name="g"),
			],
			response_format="json",
		)
		self.assertEqual(res.content, "ok")
		msgs = srv.requests[0]["body"]["messages"]
		self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user"])
		self.assertEqual(msgs[0]["content"][0]["source"], {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="})
		self.assertEqual(msgs[1]["content"][0], {"type": "tool_use", "id": "t1", "name": "f", "input": {"a": 1}})
		self.assertEqual([b["tool_use_id"] for b in msgs[2]["content"]], ["t1", "t2"])  # grouped in one user turn
		self.assertIn("valid JSON", srv.requests[0]["body"]["system"][0]["text"])

	def test_extended_thinking_request_shape(self):
		srv = ScriptedServer([(200, "application/json", json.dumps({"id": "m", "type": "message", "role": "assistant", "model": "x", "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}}).encode())])
		self.addCleanup(srv.stop)
		_anthropic(srv, thinking_budget=2048).chat([LLMMessage(role="user", content="think")], reasoning=True)
		body = srv.requests[0]["body"]
		self.assertEqual(body["thinking"], {"type": "enabled", "budget_tokens": 2048})
		self.assertGreater(body["max_tokens"], 2048)
		self.assertNotIn("temperature", body)

	def test_errors_are_provider_errors(self):
		for status, code in ((401, "auth"), (429, "rate_limited"), (529, "provider_unavailable")):
			srv = ScriptedServer([(status, "application/json", b'{"type":"error","error":{"type":"x","message":"SECRET"}}')])
			self.addCleanup(srv.stop)
			with self.assertRaises(ProviderError) as cm:
				_anthropic(srv).chat([LLMMessage(role="user", content="hi")])
			self.assertEqual(cm.exception.code, code)
			self.assertNotIn("SECRET", cm.exception.message)

	def test_missing_key_is_config_error(self):
		with self.assertRaises(ProviderError) as cm:
			AnthropicProvider(api_key="", model="m").chat([LLMMessage(role="user", content="hi")])
		self.assertEqual(cm.exception.code, "auth")

	def test_registry_picks_native_adapter(self):
		p = from_settings({"provider": "Anthropic", "api_key": "sk-ant-x", "default_model": "claude-test"})
		self.assertIsInstance(p, AnthropicProvider)
		self.assertEqual(p.model, "claude-test")
		self.assertTrue(ProviderRegistry.requires(p, "tool_calling", "vision").ok)


class _FakeProvider:
	"""Scripted event source standing in for a provider inside stream_round."""

	def __init__(self, events, raises=None):
		self.events, self.raises = events, raises
		self.closed = False

	def chat(self, messages, **kw):
		return LLMResult(content="blocking")

	def chat_events(self, messages, **kw):
		try:
			for e in self.events:
				yield e
			if self.raises:
				raise self.raises
		finally:
			self.closed = True


class TestStreamRound(IntegrationTestCase):
	def setUp(self):
		self.published: list[dict] = []
		p = mock.patch.object(
			streaming, "publish_stream",
			side_effect=lambda s, c, done=False, reset=False: self.published.append({"chunk": c, "done": done}),
		)
		p.start()
		self.addCleanup(p.stop)

	def _text(self, n):
		return [StreamEvent("text", text="abcdefghijkl") for _ in range(n)]

	def test_publishes_deltas_live_and_returns_final(self):
		final = LLMResult(content="abcdefghijkl" * 2, tokens_in=3, tokens_out=4)
		prov = _FakeProvider(self._text(2) + [StreamEvent("result", result=final)])
		with mock.patch.object(streaming, "is_cancelled", return_value=False):
			rnd = streaming.stream_round(prov, [], settings={"enable_streaming": 1}, session="S")
		self.assertTrue(rnd.streamed)
		self.assertEqual("".join(p["chunk"] for p in self.published), "abcdefghijkl" * 2)
		self.assertEqual(rnd.result.tokens_out, 4)
		self.assertTrue(prov.closed)

	def test_streaming_disabled_uses_blocking_call(self):
		rnd = streaming.stream_round(_FakeProvider([]), [], settings={"enable_streaming": 0}, session="S")
		self.assertEqual((rnd.result.content, rnd.streamed), ("blocking", False))
		self.assertEqual(self.published, [])

	def test_stop_cancels_midstream_and_keeps_partial(self):
		prov = _FakeProvider(self._text(10))
		with mock.patch.object(streaming, "is_cancelled", return_value=True):
			rnd = streaming.stream_round(prov, [], settings={"enable_streaming": 1}, session="S")
		self.assertTrue(rnd.stopped)
		self.assertEqual(rnd.result.content, "abcdefghijkl")
		self.assertTrue(prov.closed)  # provider connection released

	def test_midstream_failure_keeps_what_user_saw(self):
		prov = _FakeProvider(self._text(2), raises=ProviderError("boom", code="network", retryable=True))
		with mock.patch.object(streaming, "is_cancelled", return_value=False):
			rnd = streaming.stream_round(prov, [], settings={"enable_streaming": 1}, session="S")
		self.assertTrue(rnd.interrupted)
		self.assertEqual(rnd.result.content, "abcdefghijkl" * 2)

	def test_failure_before_any_output_propagates(self):
		prov = _FakeProvider([], raises=ProviderError("boom", code="auth"))
		with self.assertRaises(ProviderError):
			streaming.stream_round(prov, [], settings={"enable_streaming": 1}, session="S")


class TestEmbeddingEndpoint(IntegrationTestCase):
	"""Embeddings may live on another server or provider than chat; they must not inherit the chat URL."""

	def test_separate_embedding_server(self):
		p = from_settings(
			{"provider": "Custom OpenAI-compatible", "api_endpoint": "http://llm:8080/v1", "default_model": "chat-m",
			 "embedding_provider": "Custom OpenAI-compatible", "embedding_endpoint": "http://embed:8080/v1", "embedding_model": "emb-m"},
			for_embedding=True,
		)
		self.assertEqual((p.api_endpoint, p.model), ("http://embed:8080/v1", "emb-m"))

	def test_same_provider_without_its_own_endpoint_shares_the_chat_endpoint(self):
		p = from_settings(
			{"provider": "Custom OpenAI-compatible", "api_endpoint": "http://llm:8080/v1", "default_model": "chat-m",
			 "embedding_provider": "Custom OpenAI-compatible", "embedding_model": "emb-m"},
			for_embedding=True,
		)
		self.assertEqual(p.api_endpoint, "http://llm:8080/v1")

	def test_a_different_embedding_provider_never_inherits_the_chat_endpoint(self):
		p = from_settings(
			{"provider": "Custom OpenAI-compatible", "api_endpoint": "http://llm:8080/v1", "default_model": "chat-m",
			 "embedding_provider": "OpenAI", "embedding_api_key": "k"},
			for_embedding=True,
		)
		self.assertEqual(p.api_endpoint, "https://api.openai.com/v1")
		self.assertEqual(p.model, "text-embedding-3-small")  # and never the chat model's name
