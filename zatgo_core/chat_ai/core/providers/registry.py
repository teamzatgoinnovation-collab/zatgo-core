"""Provider registry and factory from settings dict (no Frappe imports)."""

from __future__ import annotations

from typing import Any

from zatgo_core.chat_ai.core.providers.base import LLMProvider
from zatgo_core.chat_ai.core.providers.capabilities import Capabilities, NegotiationResult, PROVIDER_DEFAULTS, negotiate
from zatgo_core.chat_ai.core.providers.openai_compat import OpenAICompatProvider

_REGISTRY: dict[str, type] = {}
_CUSTOM: list[LLMProvider] = []


def register_provider_class(label: str, cls: type):
	_REGISTRY[label] = cls


def register_provider_instance(provider: LLMProvider):
	_CUSTOM.append(provider)


def list_providers() -> list[str]:
	labels = list(PROVIDER_DEFAULTS.keys()) + list(_REGISTRY.keys())
	return sorted(set(labels))


def get_capabilities(label: str) -> Capabilities:
	return PROVIDER_DEFAULTS.get(label, PROVIDER_DEFAULTS["Custom OpenAI-compatible"])


_DEFAULT_MODELS = {
	"OpenAI": "gpt-4o",
	"Anthropic": "claude-sonnet-4-20250514",
	"Google Gemini": "gemini-2.0-flash",
	"Azure OpenAI": "gpt-4o",
	"Ollama": "llama3.2",
	"OpenRouter": "openrouter/auto",
	"Custom OpenAI-compatible": "gpt-4o",
}

_DEFAULT_EMBEDDING_MODELS = {
	"OpenAI": "text-embedding-3-small",
	"Google Gemini": "text-embedding-004",
	"Ollama": "nomic-embed-text",
	"OpenRouter": "openai/text-embedding-3-small",
	"Custom OpenAI-compatible": "text-embedding-3-small",
}


def from_settings(settings: dict[str, Any], *, for_embedding: bool = False) -> LLMProvider:
	"""Build provider from a plain settings dict."""
	if for_embedding:
		label = settings.get("embedding_provider") or settings.get("provider") or "OpenAI"
		api_key = settings.get("embedding_api_key") or settings.get("api_key") or ""
		label = _normalize_provider_label(label, api_key)
		model = (
			settings.get("embedding_model")
			or settings.get("default_model")
			or _DEFAULT_EMBEDDING_MODELS.get(label)
			or "text-embedding-3-small"
		)
	else:
		label = settings.get("provider") or "OpenAI"
		api_key = settings.get("api_key") or ""
		label = _normalize_provider_label(label, api_key)
		model = settings.get("default_model") or _DEFAULT_MODELS.get(label) or "gpt-4o"

	endpoint = (settings.get("api_endpoint") or "").strip() or _default_endpoint(label)
	if not endpoint:
		raise RuntimeError(
			f"API Endpoint is required for provider '{label}'. "
			"For OpenRouter set Provider to OpenRouter (or endpoint https://openrouter.ai/api/v1)."
		)
	timeout = int(settings.get("request_timeout_seconds") or 120)

	if label in _REGISTRY:
		return _REGISTRY[label](settings)

	# Anthropic uses messages API — use compat endpoint override if user set OpenAI-compat proxy,
	# else OpenAICompat with Anthropic-shaped endpoint note (users can set custom endpoint).
	return OpenAICompatProvider(
		api_key=api_key,
		api_endpoint=endpoint,
		model=model,
		temperature=float(settings.get("temperature") or 0.2),
		max_tokens=int(settings.get("max_tokens") or 2048),
		azure_deployment=settings.get("azure_deployment") or "",
		azure_api_version=settings.get("azure_api_version") or "",
		provider_label=label,
		timeout=timeout,
	)


def _normalize_provider_label(label: str, api_key: str) -> str:
	"""Map OpenRouter keys away from Custom→localhost default."""
	key = (api_key or "").strip()
	if key.startswith("sk-or-") and label in ("Custom OpenAI-compatible", "OpenAI", ""):
		return "OpenRouter"
	return label


def _default_endpoint(label: str) -> str:
	return {
		"OpenAI": "https://api.openai.com/v1",
		"Anthropic": "https://api.anthropic.com/v1",
		"Google Gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
		"Azure OpenAI": "",
		"Ollama": "http://127.0.0.1:11434/v1",
		"OpenRouter": "https://openrouter.ai/api/v1",
		# Empty on purpose — require an explicit URL (avoids silent localhost 111)
		"Custom OpenAI-compatible": "",
	}.get(label, "https://api.openai.com/v1")


def requires(provider: LLMProvider, *caps: str) -> NegotiationResult:
	return negotiate(provider.capabilities, *caps)


class ProviderRegistry:
	"""Convenience facade used by pipeline."""

	@staticmethod
	def get_active(settings: dict) -> LLMProvider:
		return from_settings(settings)

	@staticmethod
	def get_embedding(settings: dict) -> LLMProvider:
		return from_settings(settings, for_embedding=True)

	@staticmethod
	def requires(provider: LLMProvider, *caps: str) -> NegotiationResult:
		return requires(provider, *caps)

	@staticmethod
	def list_providers() -> list[str]:
		return list_providers()
