"""One-call configuration of Chat AI against self-hosted services (no external API).

    bench --site <site> execute zatgo_core.chat_ai.setup_self_hosted.configure \
        --kwargs '{"llm_url": "http://zatgo-llm:8080", "embed_url": "http://zatgo-embed:8080", "searxng_url": "http://zatgo-searxng:8080"}'

Points the chat model at a llama.cpp / vLLM / any OpenAI-compatible server, embeddings at a second
server, and web search at a SearXNG instance. Existing API keys are left alone; nothing is sent
anywhere by this function (use `check()` to probe the services).
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


def _probe(url: str, timeout: int = 8) -> str:
	try:
		with urllib.request.urlopen(url, timeout=timeout) as resp:
			return f"ok ({resp.status})"
	except urllib.error.HTTPError as exc:
		return f"http {exc.code}"
	except Exception as exc:  # unreachable, DNS, timeout
		return f"unreachable ({type(exc).__name__})"


def check() -> dict:
	"""Reachability of the configured services, from this server's point of view."""
	s = frappe.get_single("Chat AI Settings")
	base = (s.api_endpoint or "").rstrip("/")
	out = {"chat": _probe(base.removesuffix("/v1") + "/health") if base else "not configured"}
	if s.embedding_endpoint:
		out["embeddings"] = _probe(s.embedding_endpoint.rstrip("/").removesuffix("/v1") + "/health")
	if s.web_search_url and s.web_search_provider == "SearXNG":
		out["web_search"] = _probe(s.web_search_url.rstrip("/") + "/search?q=test&format=json")
	return out
