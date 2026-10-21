"""One-call configuration of Chat AI against self-hosted services (no external API).

Ollama (the default):

    bench --site <site> execute zatgo_core.chat_ai.setup_self_hosted.configure_ollama \
        --kwargs '{"ollama_url": "http://ollama:11434", "model": "llama3.2", "embed_model": "nomic-embed-text"}'

Any other OpenAI-compatible server (llama.cpp, vLLM):

    bench --site <site> execute zatgo_core.chat_ai.setup_self_hosted.configure \
        --kwargs '{"llm_url": "http://zatgo-llm:8080", "embed_url": "http://zatgo-embed:8080", "searxng_url": "http://zatgo-searxng:8080"}'

Points the chat model at the local server, embeddings at it (or a second server), and web search at a
SearXNG instance, and switches "Local models only" on. Existing API keys are left alone; nothing is
sent anywhere by these functions (use `check()` to probe the services).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import frappe

LOCAL_PROVIDER = "Custom OpenAI-compatible"  # speaks /v1/chat/completions, tools, SSE and embeddings


def _v1(url: str) -> str:
	url = (url or "").strip().rstrip("/")
	return url if url.endswith("/v1") else url + "/v1"


def configure(
	llm_url: str,
	model: str = "qwen2.5-3b",
	embed_url: str | None = None,
	embed_model: str = "nomic-embed-text",
	searxng_url: str | None = None,
	context_window_tokens: int = 8192,
	request_timeout_seconds: int = 300,
) -> dict:
	"""Apply the self-hosted setup to Chat AI Settings and return what was set."""
	if not (llm_url or "").startswith(("http://", "https://")):
		frappe.throw("llm_url must be an http(s) URL")
	values = {
		"provider": LOCAL_PROVIDER,
		"api_endpoint": _v1(llm_url),
		"default_model": model,
		# A small local model has a small window: budget history for it and give CPU inference time.
		"context_window_tokens": int(context_window_tokens),
		"request_timeout_seconds": int(request_timeout_seconds),
		"max_tokens": 1024,
		"enable_streaming": 1,
		"enable_tool_calling": 1,
		"enable_model_routing": 0,
	}
	if embed_url:
		values.update(embedding_provider=LOCAL_PROVIDER, embedding_endpoint=_v1(embed_url), embedding_model=embed_model)
	if searxng_url:
		values.update(enable_web_search=1, web_search_provider="SearXNG", web_search_url=searxng_url.strip().rstrip("/"))
	doc = frappe.get_doc("Chat AI Settings")
	doc.update(values)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return values


def configure_ollama(
	ollama_url: str = "http://127.0.0.1:11434",
	model: str = "llama3.2",
	embed_model: str | None = "nomic-embed-text",
	searxng_url: str | None = None,
	context_window_tokens: int = 4096,
	request_timeout_seconds: int = 300,
) -> dict:
	"""Point Chat AI at an Ollama server and switch 'Local models only' on.

	`context_window_tokens` is what ZatGo AI budgets history for; it must not exceed the context Ollama
	really runs the model with (its default is 4096; raise it with OLLAMA_CONTEXT_LENGTH or a Modelfile
	`num_ctx` -- the OpenAI-compatible /v1 API can't set it per request)."""
	if not (ollama_url or "").startswith(("http://", "https://")):
		frappe.throw("ollama_url must be an http(s) URL")
	endpoint = _v1(ollama_url)
	values = {
		"local_only": 1,
		"provider": "Ollama",
		"api_endpoint": endpoint,
		"default_model": model,
		"context_window_tokens": int(context_window_tokens),
		"request_timeout_seconds": int(request_timeout_seconds),
		"max_tokens": 1024,
		"enable_streaming": 1,
		"enable_tool_calling": 1,
		"enable_model_routing": 0,
	}
	if embed_model:
		values.update(embedding_provider="Ollama", embedding_endpoint=endpoint, embedding_model=embed_model)
	if searxng_url:
		values.update(enable_web_search=1, web_search_provider="SearXNG", web_search_url=searxng_url.strip().rstrip("/"))
	doc = frappe.get_doc("Chat AI Settings")
	doc.update(values)
	doc.save(ignore_permissions=True)  # validate() refuses anything that isn't on your own network
	frappe.db.commit()
	return values


def _probe(url: str, timeout: int = 8) -> str:
	try:
		with urllib.request.urlopen(url, timeout=timeout) as resp:
			return f"ok ({resp.status})"
	except urllib.error.HTTPError as exc:
		return f"http {exc.code}"
	except Exception as exc:  # unreachable, DNS, timeout
		return f"unreachable ({type(exc).__name__})"


def _get_json(url: str, timeout: int = 8):
	try:
		with urllib.request.urlopen(url, timeout=timeout) as resp:
			return json.loads(resp.read().decode("utf-8", "replace"))
	except Exception:
		return None


def _ollama_models(root: str) -> list[str] | None:
	"""Model names an Ollama server has pulled (None = unreachable)."""
	data = _get_json(root + "/api/tags")
	if not isinstance(data, dict):
		return None
	return [m.get("name", "") for m in data.get("models", [])]


def _has_model(pulled: list[str], wanted: str) -> bool:
	wanted = (wanted or "").strip()
	return bool(wanted) and any(n == wanted or n == f"{wanted}:latest" or n.split(":")[0] == wanted for n in pulled)


def check() -> dict:
	"""Reachability of the configured services, from this server's point of view.
	Ollama has no /health: it is probed through /api/tags, which also tells whether the configured
	chat and embedding models have been pulled."""
	s = frappe.get_single("Chat AI Settings")
	base = (s.api_endpoint or "").rstrip("/")
	if not base and s.provider == "Ollama":
		base = "http://127.0.0.1:11434/v1"
	out: dict = {"local_only": bool(s.local_only) if s.local_only is not None else True}
	root = base.removesuffix("/v1")
	if not base:
		out["chat"] = "not configured"
	elif s.provider == "Ollama":
		pulled = _ollama_models(root)
		out["chat"] = "unreachable" if pulled is None else ("ok" if _has_model(pulled, s.default_model or "llama3.2") else f"model not pulled: {s.default_model or 'llama3.2'}")
		if s.embedding_provider == "Ollama":
			emb = (s.embedding_endpoint or base).rstrip("/").removesuffix("/v1")
			pulled_e = pulled if emb == root else _ollama_models(emb)
			out["embeddings"] = "unreachable" if pulled_e is None else ("ok" if _has_model(pulled_e, s.embedding_model or "nomic-embed-text") else f"model not pulled: {s.embedding_model or 'nomic-embed-text'}")
	else:
		out["chat"] = _probe(root + "/health")
		if s.embedding_endpoint:
			out["embeddings"] = _probe(s.embedding_endpoint.rstrip("/").removesuffix("/v1") + "/health")
	if s.web_search_url and s.web_search_provider == "SearXNG":
		out["web_search"] = _probe(s.web_search_url.rstrip("/") + "/search?q=test&format=json")
	return out
