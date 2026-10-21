"""'Local models only': ZatGo AI must not send prompts, documents or embeddings to an
external API. No Frappe imports, so the provider factory and the tests use it as is.

The rule is about WHERE a request goes, not which provider label is picked: an endpoint is
allowed when its host is on a private network -- loopback, RFC 1918, link-local, a bare
container / service name (`ollama`, `zatgo-llm`), `host.docker.internal`, `*.local` /
`*.internal` / `*.lan` / `*.localhost` / `*.test`, or any other name whose DNS answer is
private only. Anything else (api.openai.com, api.anthropic.com, openrouter.ai, a public IP,
a name that fails to resolve) is refused.

The switch is Chat AI Settings -> "Local models only". It is ON unless a site has
explicitly turned it off (`local_only` missing or None counts as on), so a site that was
never configured can not leak by default.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

LOCAL_SUFFIXES = (".local", ".internal", ".lan", ".localhost", ".test", ".home.arpa")
LOCAL_NAMES = {"localhost", "host.docker.internal", "host.containers.internal"}
OLLAMA_DEFAULT_ENDPOINT = "http://127.0.0.1:11434/v1"


class ExternalEndpointError(RuntimeError):
	"""An endpoint that leaves the private network while 'Local models only' is on."""


def is_enabled(settings: dict) -> bool:
	"""'Local models only' is on unless explicitly switched off (0 / "0" / False)."""
	value = settings.get("local_only")
	if value is None or value == "":
		return True
	return str(value).strip().lower() not in ("0", "false", "no", "off")


def _is_private_ip(text: str) -> bool:
	try:
		ip = ipaddress.ip_address(text.split("%", 1)[0])
	except ValueError:
		return False
	return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_unspecified


def _resolves_private_only(host: str) -> bool:
	try:
		infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
	except OSError:
		return False  # can't prove it is private -> not allowed
	addrs = {info[4][0] for info in infos}
	return bool(addrs) and all(_is_private_ip(a) for a in addrs)


def is_local_url(url: str) -> bool:
	"""True when [url]'s host is on a private network (see module doc)."""
	url = (url or "").strip()
	if not url:
		return False
	parsed = urlparse(url if "://" in url else f"http://{url}")
	if parsed.scheme not in ("http", "https"):
		return False
	host = (parsed.hostname or "").strip().lower().rstrip(".")
	if not host:
		return False
	if host in LOCAL_NAMES:
		return True
	if _is_private_ip(host):
		return True
	try:
		ipaddress.ip_address(host)
		return False  # a public IP literal
	except ValueError:
		pass
	if "." not in host or host.endswith(LOCAL_SUFFIXES):
		return True  # bare service / container name or a local-only suffix
	return _resolves_private_only(host)


def assert_local(url: str, *, what: str = "model endpoint") -> str:
	"""Return [url], or raise ExternalEndpointError with an actionable message."""
	if is_local_url(url):
		return url
	raise ExternalEndpointError(
		f"'Local models only' is on, so the {what} must be on your own network "
		f"(got {url or 'the provider default, which is an external API'}). "
		"Set Provider to Ollama (or a Custom OpenAI-compatible local server) and its URL, "
		"e.g. http://ollama:11434/v1. An administrator can untick 'Local models only' in "
		"Chat AI Settings to allow external APIs."
	)


def check_settings(settings: dict) -> list[str]:
	"""Every way [settings] would reach an external host, as messages (empty = all local).
	Used when Chat AI Settings is saved; the provider factory enforces the same at call time."""
	if not is_enabled(settings):
		return []
	problems: list[str] = []
	# With 'Local models only' on, an unset provider means Ollama (see registry.from_settings).
	provider = settings.get("provider") or "Ollama"
	chat = (settings.get("api_endpoint") or "").strip() or (OLLAMA_DEFAULT_ENDPOINT if provider == "Ollama" else "")
	if not chat or not is_local_url(chat):
		problems.append(_describe("Chat endpoint", chat))
	if settings.get("embedding_provider"):
		emb = (settings.get("embedding_endpoint") or "").strip()
		if not emb and settings.get("embedding_provider") == provider:
			emb = chat  # inherits the chat endpoint
		if not emb and settings.get("embedding_provider") == "Ollama":
			emb = OLLAMA_DEFAULT_ENDPOINT
		if not emb or not is_local_url(emb):
			problems.append(_describe("Embedding endpoint", emb))
	if settings.get("enable_web_search"):
		if (settings.get("web_search_provider") or "SearXNG") == "Brave":
			problems.append("Web search provider Brave is an external API: use SearXNG on your own network.")
		elif not is_local_url(settings.get("web_search_url") or ""):
			problems.append(_describe("SearXNG URL", (settings.get("web_search_url") or "").strip()))
	voicebox = (settings.get("voicebox_url") or "").strip()
	if voicebox and settings.get("tts_engine", "Voicebox") == "Voicebox" and not is_local_url(voicebox):
		problems.append(_describe("Voicebox URL", voicebox))
	return problems


def _describe(label: str, url: str) -> str:
	if not url:
		return f"{label} is empty: set it to your local server, e.g. http://ollama:11434/v1."
	return f"{label} {url} is not on your own network."
