"""Shared OpenAI-compatible HTTP client (stdlib urllib — no extra deps)."""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from typing import Any, Iterator

from zatgo_core.chat_ai.core.providers.base import LLMMessage, LLMProvider, LLMResult, StreamEvent
from zatgo_core.chat_ai.core.providers.capabilities import PROVIDER_DEFAULTS
from zatgo_core.chat_ai.core.providers.errors import ProviderError, from_exception, from_http_status


class OpenAICompatProvider(LLMProvider):
	"""Works with OpenAI, Azure OpenAI, Ollama, OpenRouter, and custom endpoints."""

	name = "OpenAI"

	def __init__(
		self,
		*,
		api_key: str = "",
		api_endpoint: str = "https://api.openai.com/v1",
		model: str = "gpt-4o",
		temperature: float = 0.2,
		max_tokens: int = 2048,
		azure_deployment: str = "",
		azure_api_version: str = "",
		provider_label: str = "OpenAI",
		timeout: int = 120,
	):
		self.api_key = api_key or ""
		self.api_endpoint = (api_endpoint or "https://api.openai.com/v1").rstrip("/")
		self.model = model
		self.temperature = temperature
		self.max_tokens = max_tokens
		self.azure_deployment = azure_deployment
		self.azure_api_version = azure_api_version
		self.name = provider_label
		self.timeout = timeout
		self.capabilities = PROVIDER_DEFAULTS.get(provider_label, PROVIDER_DEFAULTS["Custom OpenAI-compatible"])

	def _headers(self) -> dict[str, str]:
		headers = {"Content-Type": "application/json"}
		if self.api_key:
			headers["Authorization"] = f"Bearer {self.api_key}"
		if self.name == "OpenRouter":
			headers["HTTP-Referer"] = "https://chat-ai.local"
		return headers

	def _chat_url(self) -> str:
		if self.name == "Azure OpenAI" and self.azure_deployment:
			base = self.api_endpoint
			ver = self.azure_api_version or "2024-02-15-preview"
			return f"{base}/openai/deployments/{self.azure_deployment}/chat/completions?api-version={ver}"
		return f"{self.api_endpoint}/chat/completions"

	def _embed_url(self) -> str:
		return f"{self.api_endpoint}/embeddings"

	@staticmethod
	def _serialize_messages(messages: list[LLMMessage]) -> list[dict]:
		out = []
		for m in messages:
			item: dict[str, Any] = {"role": m.role, "content": m.content or ""}
			if m.name:
				item["name"] = m.name
			if m.tool_call_id:
				item["tool_call_id"] = m.tool_call_id
			if m.tool_calls:
				item["tool_calls"] = m.tool_calls
			if m.images:
				content = [{"type": "text", "text": m.content or ""}]
				for url in m.images:
					content.append({"type": "image_url", "image_url": {"url": url}})
				item["content"] = content
			out.append(item)
		return out

	def _post(self, url: str, payload: dict) -> dict:
		data = json.dumps(payload).encode("utf-8")
		req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
		try:
			with urllib.request.urlopen(req, timeout=self.timeout) as resp:
				return json.loads(resp.read().decode("utf-8"))
		except urllib.error.HTTPError as exc:
			body = exc.read().decode("utf-8", errors="replace")
			raise from_http_status(exc.code, body[:500]) from exc
		except (urllib.error.URLError, OSError) as exc:
			raise from_exception(exc) from exc

	def _build_payload(
		self,
		messages: list[LLMMessage],
		*,
		tools: list[dict] | None = None,
		stream: bool = False,
		response_format: str | None = None,
		**opts: Any,
	) -> dict[str, Any]:
		payload: dict[str, Any] = {
			"model": self.model,
			"messages": self._serialize_messages(messages),
			"temperature": self.temperature,
			"max_tokens": self.max_tokens,
		}
		if stream:
			payload["stream"] = True
		if tools and self.capabilities.tool_calling:
			payload["tools"] = tools
			payload["tool_choice"] = opts.get("tool_choice", "auto")
		if response_format == "json" and self.capabilities.json_output:
			payload["response_format"] = {"type": "json_object"}
		return payload

	def chat(
		self,
		messages: list[LLMMessage],
		*,
		tools: list[dict] | None = None,
		stream: bool = False,
		response_format: str | None = None,
		reasoning: bool = False,
		**opts: Any,
	) -> LLMResult:
		payload = self._build_payload(
			messages, tools=tools, stream=False, response_format=response_format, **opts
		)
		raw = self._post(self._chat_url(), payload)
		choice = (raw.get("choices") or [{}])[0]
		message = choice.get("message") or {}
		usage = raw.get("usage") or {}
		return LLMResult(
			content=message.get("content") or "",
			tool_calls=message.get("tool_calls") or [],
			tokens_in=int(usage.get("prompt_tokens") or 0),
			tokens_out=int(usage.get("completion_tokens") or 0),
			raw=raw,
			model=raw.get("model") or self.model,
		)

	def chat_stream(self, messages: list[LLMMessage], **opts: Any) -> Iterator[str]:
		"""Yield content deltas from OpenAI-compatible SSE streaming."""
		if not getattr(self.capabilities, "streaming", True):
			result = self.chat(messages, stream=False, **opts)
			text = result.content or ""
			if text:
				yield text
			return

		payload = self._build_payload(messages, stream=True, **opts)
		# Do not attach tools on stream path — final narrative only
		payload.pop("tools", None)
		payload.pop("tool_choice", None)
		data = json.dumps(payload).encode("utf-8")
		headers = self._headers()
		headers["Accept"] = "text/event-stream"
		req = urllib.request.Request(self._chat_url(), data=data, headers=headers, method="POST")
		try:
			with urllib.request.urlopen(req, timeout=self.timeout) as resp:
				while True:
					raw_line = resp.readline()
					if not raw_line:
						break
					line = raw_line.decode("utf-8", errors="replace").strip()
					if not line or line.startswith(":"):
						continue
					if not line.startswith("data:"):
						continue
					data_str = line[5:].strip()
					if data_str == "[DONE]":
						break
					try:
						obj = json.loads(data_str)
					except json.JSONDecodeError:
						continue
					choice = (obj.get("choices") or [{}])[0]
					delta = choice.get("delta") or {}
					piece = delta.get("content")
					if piece:
						yield piece
		except urllib.error.HTTPError as exc:
			body = exc.read().decode("utf-8", errors="replace")
			# Fallback to non-stream if provider rejects stream
			if exc.code in (400, 404, 501):
				result = self.chat(messages, stream=False, **opts)
				text = result.content or ""
				if text:
					yield text
				return
			raise from_http_status(exc.code, body[:500]) from exc
		except Exception:
			result = self.chat(messages, stream=False, **opts)
			text = result.content or ""
			if text:
				yield text

	def chat_events(
		self,
		messages: list[LLMMessage],
		*,
		tools: list[dict] | None = None,
		response_format: str | None = None,
		reasoning: bool = False,
		**opts: Any,
	) -> Iterator[StreamEvent]:
		"""SSE streaming with tool calls: yields text deltas as they arrive, then
		one "result" event with the assembled content, tool_calls and usage."""
		if not getattr(self.capabilities, "streaming", True):
			yield from super().chat_events(
				messages, tools=tools, response_format=response_format, reasoning=reasoning, **opts
			)
			return
		payload = self._build_payload(
			messages, tools=tools, stream=True, response_format=response_format, **opts
		)
		payload["stream_options"] = {"include_usage": True}
		headers = self._headers()
		headers["Accept"] = "text/event-stream"
		req = urllib.request.Request(
			self._chat_url(), data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
		)
		content: list[str] = []
		calls: dict[int, dict] = {}
		usage: dict = {}
		model = self.model
		finished = False  # saw [DONE] or a finish_reason: the provider really ended the answer
		try:
			resp = urllib.request.urlopen(req, timeout=self.timeout)
		except urllib.error.HTTPError as exc:
			body = exc.read().decode("utf-8", errors="replace")
			if exc.code in (400, 404, 501) and "stream_options" in body.lower():
				payload.pop("stream_options", None)  # provider rejects usage-in-stream; retry plain
				req = urllib.request.Request(
					self._chat_url(), data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
				)
				try:
					resp = urllib.request.urlopen(req, timeout=self.timeout)
				except urllib.error.HTTPError as exc2:
					raise from_http_status(exc2.code, exc2.read().decode("utf-8", errors="replace")[:500]) from exc2
			else:
				raise from_http_status(exc.code, body[:500]) from exc
		except (urllib.error.URLError, OSError) as exc:
			raise from_exception(exc) from exc
		try:
			with resp:
				while True:
					raw_line = resp.readline()
					if not raw_line:
						break
					line = raw_line.decode("utf-8", errors="replace").strip()
					if not line.startswith("data:"):
						continue
					data_str = line[5:].strip()
					if data_str == "[DONE]":
						finished = True
						break
					try:
						obj = json.loads(data_str)
					except json.JSONDecodeError:
						continue
					model = obj.get("model") or model
					if obj.get("usage"):
						usage = obj["usage"]
					for choice in obj.get("choices") or []:
						if choice.get("finish_reason"):
							finished = True
						delta = choice.get("delta") or {}
						text = delta.get("content")
						if text:
							content.append(text)
							yield StreamEvent("text", text=text)
						for tc in delta.get("tool_calls") or []:
							slot = calls.setdefault(
								tc.get("index", 0),
								{"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
							)
							if tc.get("id"):
								slot["id"] = tc["id"]
							fn = tc.get("function") or {}
							if fn.get("name"):
								slot["function"]["name"] += fn["name"]
							if fn.get("arguments"):
								slot["function"]["arguments"] += fn["arguments"]
		except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
			raise from_exception(exc) from exc
		if not finished:
			# The connection ended without the provider finishing: never present this as a complete answer.
			raise ProviderError(
				"The connection to the AI provider was interrupted.", code="interrupted", retryable=True
			)
		yield StreamEvent(
			"result",
			result=LLMResult(
				content="".join(content),
				tool_calls=[calls[i] for i in sorted(calls)],
				tokens_in=int(usage.get("prompt_tokens") or 0),
				tokens_out=int(usage.get("completion_tokens") or 0),
				model=model,
			),
		)

	def embed(self, texts: list[str]) -> list[list[float]]:
		if not self.capabilities.embedding:
			raise NotImplementedError(f"{self.name} embedding not available")
		payload = {"model": self.model, "input": texts}
		raw = self._post(self._embed_url(), payload)
		data = raw.get("data") or []
		return [row.get("embedding") or [] for row in data]
