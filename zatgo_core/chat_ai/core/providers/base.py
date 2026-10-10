"""LLMProvider protocol — common capability interface."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator

from zatgo_core.chat_ai.core.providers.capabilities import Capabilities


@dataclass
class LLMMessage:
	role: str
	content: str
	name: str | None = None
	tool_call_id: str | None = None
	tool_calls: list[dict] | None = None
	images: list[str] | None = None


@dataclass
class LLMResult:
	content: str = ""
	tool_calls: list[dict] = field(default_factory=list)
	tokens_in: int = 0
	tokens_out: int = 0
	raw: dict = field(default_factory=dict)
	model: str = ""


class LLMProvider(ABC):
	name: str = "base"
	capabilities: Capabilities = Capabilities()

	@abstractmethod
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
		...

	def chat_stream(self, messages: list[LLMMessage], **opts: Any) -> Iterator[str]:
		result = self.chat(messages, stream=False, **opts)
		yield result.content

	def embed(self, texts: list[str]) -> list[list[float]]:
		raise NotImplementedError(f"{self.name} does not support embedding")

	def ping(self) -> tuple[bool, int, str]:
		"""Return (ok, latency_ms, error)."""
		import time
		start = time.time()
		try:
			self.chat([LLMMessage(role="user", content="ping")], tools=None)
			return True, int((time.time() - start) * 1000), ""
		except Exception as exc:
			return False, int((time.time() - start) * 1000), str(exc)
