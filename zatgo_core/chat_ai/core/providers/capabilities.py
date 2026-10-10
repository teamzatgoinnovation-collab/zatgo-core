"""LLM capability flags and negotiation."""

from __future__ import annotations
from dataclasses import dataclass, field


CAPABILITIES = (
	"chat",
	"embedding",
	"tool_calling",
	"streaming",
	"vision",
	"reasoning",
	"json_output",
)


@dataclass
class Capabilities:
	chat: bool = True
	embedding: bool = False
	tool_calling: bool = False
	streaming: bool = False
	vision: bool = False
	reasoning: bool = False
	json_output: bool = False

	def as_dict(self) -> dict:
		return {k: bool(getattr(self, k)) for k in CAPABILITIES}

	def supports(self, *names: str) -> bool:
		return all(bool(getattr(self, n, False)) for n in names)


# Known defaults (model-dependent ones are optimistic; discovery may refine)
PROVIDER_DEFAULTS: dict[str, Capabilities] = {
	"OpenAI": Capabilities(chat=True, embedding=True, tool_calling=True, streaming=True, vision=True, reasoning=True, json_output=True),
	"Anthropic": Capabilities(chat=True, embedding=False, tool_calling=True, streaming=True, vision=True, reasoning=True, json_output=True),
	"Google Gemini": Capabilities(chat=True, embedding=True, tool_calling=True, streaming=True, vision=True, reasoning=True, json_output=True),
	"Azure OpenAI": Capabilities(chat=True, embedding=True, tool_calling=True, streaming=True, vision=True, reasoning=False, json_output=True),
	"Ollama": Capabilities(chat=True, embedding=True, tool_calling=True, streaming=True, vision=False, reasoning=False, json_output=False),
	"OpenRouter": Capabilities(chat=True, embedding=False, tool_calling=True, streaming=True, vision=True, reasoning=True, json_output=True),
	"Custom OpenAI-compatible": Capabilities(chat=True, embedding=True, tool_calling=True, streaming=True, vision=False, reasoning=False, json_output=True),
}


@dataclass
class NegotiationResult:
	ok: bool
	missing: list[str] = field(default_factory=list)
	capabilities: Capabilities = field(default_factory=Capabilities)


def negotiate(caps: Capabilities, *required: str) -> NegotiationResult:
	missing = [r for r in required if not getattr(caps, r, False)]
	return NegotiationResult(ok=not missing, missing=missing, capabilities=caps)
