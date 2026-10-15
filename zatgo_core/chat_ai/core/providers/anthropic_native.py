"""Native Anthropic Messages API adapter (official SDK).

Unlike the OpenAI-compat endpoint this keeps native tool use, vision/document
blocks, prompt caching and extended thinking. It speaks the orchestrator's
OpenAI-shaped language at the boundary (tool schemas in, tool_calls out), so
nothing above the provider layer changes.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Iterator

from zatgo_core.chat_ai.core.providers.base import LLMMessage, LLMProvider, LLMResult, StreamEvent
from zatgo_core.chat_ai.core.providers.capabilities import PROVIDER_DEFAULTS
from zatgo_core.chat_ai.core.providers.errors import ProviderError, from_exception, from_http_status

DEFAULT_BASE_URL = "https://api.anthropic.com"
_DATA_URL = re.compile(r"^data:(?P<mime>[\w.+/-]+);base64,(?P<data>.+)$", re.S)
_JSON_HINT = "Respond with a single valid JSON object and nothing else."


def sdk_available() -> bool:
	try:
		import anthropic  # noqa: F401

		return True
	except ImportError:
		return False


def normalize_base_url(endpoint: str | None) -> str:
	"""The SDK appends /v1/messages itself; settings written for the OpenAI-compat
	endpoint end in /v1."""
	url = (endpoint or "").strip().rstrip("/")
	if not url:
		return DEFAULT_BASE_URL
	return url[:-3] if url.endswith("/v1") else url


class AnthropicProvider(LLMProvider):
	name = "Anthropic"
	capabilities = PROVIDER_DEFAULTS["Anthropic"]

	def __init__(
		self,
		*,
		api_key: str = "",
		api_endpoint: str = "",
		model: str,
		temperature: float = 0.2,
		max_tokens: int = 2048,
		timeout: int = 120,
		thinking_budget: int = 0,
		cache_system: bool = True,
	):
		self.api_key = api_key
		self.base_url = normalize_base_url(api_endpoint)
		self.model = model
		self.temperature = temperature
		self.max_tokens = max_tokens
		self.timeout = timeout
		self.thinking_budget = thinking_budget
		self.cache_system = cache_system
		self._client = None

	# -- client ---------------------------------------------------------
	def _sdk(self):
		if self._client is None:
			if not self.api_key:
				raise ProviderError(
					"No Anthropic API key is configured. Ask an administrator to set it in Chat AI Settings.",
					code="auth",
				)
			try:
				import anthropic
			except ImportError as exc:
				raise ProviderError(
					"The Anthropic SDK is not installed on this server.", code="not_configured", detail=str(exc)
				) from exc
			# Retries are the orchestrator's decision (max_retries setting), not the SDK's.
			self._client = anthropic.Anthropic(
				api_key=self.api_key, base_url=self.base_url, timeout=self.timeout, max_retries=0
			)
		return self._client

	@staticmethod
	def _wrap(exc: Exception) -> ProviderError:
		import anthropic

		if isinstance(exc, ProviderError):
			return exc
		if isinstance(exc, anthropic.APIStatusError):
			return from_http_status(exc.status_code, str(getattr(exc, "body", "") or exc)[:500])
		if isinstance(exc, anthropic.APITimeoutError):
			return from_exception(TimeoutError(str(exc)))
		return from_exception(exc)

	# -- request building -----------------------------------------------
	@staticmethod
	def _image_block(ref: str) -> dict | None:
		m = _DATA_URL.match(ref or "")
		if m:
			return {"type": "image", "source": {"type": "base64", "media_type": m["mime"], "data": m["data"]}}
		if (ref or "").startswith(("http://", "https://")):
			return {"type": "image", "source": {"type": "url", "url": ref}}
		return None

	def _convert(self, messages: list[LLMMessage], response_format: str | None) -> tuple[list[dict], list[dict]]:
		system_parts: list[str] = []
		out: list[dict] = []

		def push(role: str, blocks: list[dict]):
			if out and out[-1]["role"] == role:  # the API wants strictly alternating roles
				out[-1]["content"].extend(blocks)
			else:
				out.append({"role": role, "content": list(blocks)})

		for m in messages:
			if m.role == "system":
				if m.content:
					system_parts.append(m.content)
			elif m.role == "tool":
				push(
					"user",
					[
						{
							"type": "tool_result",
							"tool_use_id": m.tool_call_id or "",
							"content": m.content or "",
						}
					],
				)
			elif m.role == "assistant":
				blocks: list[dict] = []
				if m.content:
					blocks.append({"type": "text", "text": m.content})
				for tc in m.tool_calls or []:
					fn = tc.get("function") or {}
					raw = fn.get("arguments") or "{}"
					try:
						args = json.loads(raw) if isinstance(raw, str) else (raw or {})
					except json.JSONDecodeError:
						args = {}
					blocks.append(
						{"type": "tool_use", "id": tc.get("id") or "", "name": fn.get("name") or "", "input": args}
					)
				if blocks:
					push("assistant", blocks)
			else:
				blocks = []
				for ref in m.images or []:
					block = self._image_block(ref)
					if block:
						blocks.append(block)
				blocks.append({"type": "text", "text": m.content or ""})
				push("user", blocks)

		if response_format == "json":
			system_parts.append(_JSON_HINT)
		system: list[dict] = []
		if system_parts:
			block: dict[str, Any] = {"type": "text", "text": "\n\n".join(system_parts)}
			if self.cache_system:
				block["cache_control"] = {"type": "ephemeral"}
			system.append(block)
		return system, out

	@staticmethod
	def _convert_tools(tools: list[dict] | None) -> list[dict]:
		out = []
		for t in tools or []:
			fn = t.get("function") or t
			out.append(
				{
					"name": fn.get("name"),
					"description": fn.get("description") or "",
					"input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
				}
			)
		return out

	def _request(self, messages, tools, response_format, reasoning, opts) -> dict:
		system, converted = self._convert(messages, response_format)
		kw: dict[str, Any] = {
			"model": self.model,
			"max_tokens": int(opts.get("max_tokens") or self.max_tokens),
			"messages": converted,
		}
		if system:
			kw["system"] = system
		sdk_tools = self._convert_tools(tools)
		if sdk_tools:
			kw["tools"] = sdk_tools
			kw["tool_choice"] = {"type": "auto"}
		budget = int(opts.get("thinking_budget") or self.thinking_budget or 0)
		if reasoning and budget >= 1024:
			# Extended thinking requires max_tokens > budget and no custom temperature.
			kw["thinking"] = {"type": "enabled", "budget_tokens": budget}
			kw["max_tokens"] = max(kw["max_tokens"], budget + 1024)
		# No temperature: current Claude models (and the SDK) don't accept sampling
		# parameters, so the temperature setting only applies to OpenAI-style providers.
		return kw

	@staticmethod
	def _to_result(msg) -> LLMResult:
		text, calls = [], []
		for block in msg.content or []:
			if block.type == "text":
				text.append(block.text)
			elif block.type == "tool_use":
				calls.append(
					{
						"id": block.id,
						"type": "function",
						"function": {"name": block.name, "arguments": json.dumps(block.input or {})},
					}
				)
		usage = getattr(msg, "usage", None)
		return LLMResult(
			content="".join(text),
			tool_calls=calls,
			tokens_in=int(getattr(usage, "input_tokens", 0) or 0),
			tokens_out=int(getattr(usage, "output_tokens", 0) or 0),
			raw={"stop_reason": getattr(msg, "stop_reason", None)},
			model=getattr(msg, "model", None) or "",
		)

	# -- LLMProvider ----------------------------------------------------
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
		kw = self._request(messages, tools, response_format, reasoning, opts)
		try:
			return self._to_result(self._sdk().messages.create(**kw))
		except Exception as exc:
			raise self._wrap(exc) from exc

	def chat_events(
		self,
		messages: list[LLMMessage],
		*,
		tools: list[dict] | None = None,
		response_format: str | None = None,
		reasoning: bool = False,
		**opts: Any,
	) -> Iterator[StreamEvent]:
		kw = self._request(messages, tools, response_format, reasoning, opts)
		try:
			with self._sdk().messages.stream(**kw) as stream:
				for event in stream:
					if event.type != "content_block_delta":
						continue
					delta = event.delta
					if delta.type == "text_delta" and delta.text:
						yield StreamEvent("text", text=delta.text)
					elif delta.type == "thinking_delta" and getattr(delta, "thinking", ""):
						yield StreamEvent("reasoning", text=delta.thinking)
				final = stream.get_final_message()
		except Exception as exc:
			raise self._wrap(exc) from exc
		yield StreamEvent("result", result=self._to_result(final))

	def chat_stream(self, messages: list[LLMMessage], **opts: Any) -> Iterator[str]:
		for ev in self.chat_events(messages, **opts):
			if ev.kind == "text":
				yield ev.text

	@staticmethod
	def file_block(data: bytes, mime: str) -> dict:
		"""Document block for PDFs (native PDF understanding); used by the files pipeline."""
		return {
			"type": "document",
			"source": {"type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()},
		}
