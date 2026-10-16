"""Web search / fetch: provider interface, Brave implementation, SSRF-safe fetch.

Results carry title, url and domain straight from the provider; nothing here
invents a source. Pure python (urllib) -- Frappe settings are passed in.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from html.parser import HTMLParser

from zatgo_core.chat_ai.core.providers.errors import ProviderError, from_exception, from_http_status

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_FETCH_BYTES = 1_500_000
MAX_FETCH_CHARS = 12000
MAX_REDIRECTS = 3


class WebToolError(ValueError):
	"""User-facing failure of a web tool."""


@dataclass
class SearchResult:
	title: str
	url: str
	domain: str
	snippet: str
	age: str = ""

	def as_dict(self) -> dict:
		return asdict(self)


def domain_of(url: str) -> str:
	host = urllib.parse.urlparse(url).hostname or ""
	return host[4:] if host.startswith("www.") else host


class WebSearchProvider(ABC):
	name = "base"

	@abstractmethod
	def search(self, query: str, count: int = 5) -> list[SearchResult]:
		...


class BraveSearch(WebSearchProvider):
	name = "Brave"

	def __init__(self, api_key: str, *, endpoint: str | None = None, timeout: int = 15):
		self.api_key, self.endpoint, self.timeout = api_key, endpoint or BRAVE_URL, timeout

	def search(self, query: str, count: int = 5) -> list[SearchResult]:
		if not self.api_key:
			raise WebToolError("Web search is not configured: no API key is set in Chat AI Settings.")
		q = urllib.parse.urlencode({"q": query[:400], "count": max(1, min(int(count or 5), 10))})
		req = urllib.request.Request(
			f"{self.endpoint}?{q}",
			headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
		)
		try:
			with urllib.request.urlopen(req, timeout=self.timeout) as resp:
				data = json.loads(resp.read().decode("utf-8"))
		except urllib.error.HTTPError as exc:
			raise from_http_status(exc.code, exc.read().decode("utf-8", "replace")[:300]) from exc
		except (urllib.error.URLError, OSError, ValueError) as exc:
			raise from_exception(exc) from exc
		results = []
		for item in (data.get("web") or {}).get("results") or []:
			url = item.get("url") or ""
			if not url.startswith(("http://", "https://")):
				continue
			results.append(
				SearchResult(
					title=_strip_tags(item.get("title") or url),
					url=url,
					domain=domain_of(url),
					snippet=_strip_tags(item.get("description") or ""),
					age=item.get("age") or item.get("page_age") or "",
				)
			)
		return results


def get_provider(settings: dict) -> WebSearchProvider:
	if not settings.get("enable_web_search"):
		raise WebToolError("Web search is turned off.")
	name = settings.get("web_search_provider") or "Brave"
	if name == "Brave":
		return BraveSearch(settings.get("web_search_api_key") or "")
	raise WebToolError(f"Unknown web search provider '{name}'.")


# -- fetching ---------------------------------------------------------------

def _is_public_ip(ip: str) -> bool:
	a = ipaddress.ip_address(ip)
	# is_global is False for every range that is not publicly routable, including ones that
	# is_private misses: carrier-grade NAT 100.64.0.0/10 (cloud metadata services, Tailscale),
	# 192.0.0.0/24 and the documentation / benchmarking blocks.
	return a.is_global and not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified)


def assert_public_url(url: str) -> list[str]:
	"""Reject non-http(s) URLs, credentials in the URL and any host that resolves to a
	private/internal address. Returns the resolved IPs (for connection pinning)."""
	parts = urllib.parse.urlparse(url)
	if parts.scheme not in ("http", "https") or not parts.hostname:
		raise WebToolError("Only http(s) URLs can be fetched.")
	if parts.username or parts.password:
		raise WebToolError("URLs with credentials are not allowed.")
	try:
		port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
	except ValueError as exc:  # non-numeric or out of range
		raise WebToolError("That port is not allowed.") from exc
	if port not in (80, 443, 8080, 8443):
		raise WebToolError("That port is not allowed.")
	try:
		infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
	except socket.gaierror as exc:
		raise WebToolError("The address could not be resolved.") from exc
	ips = list({i[4][0] for i in infos})
	if not ips or not all(_is_public_ip(ip) for ip in ips):
		raise WebToolError("That address is not publicly reachable.")
	return ips


class _NoRedirect(urllib.request.HTTPRedirectHandler):
	def redirect_request(self, *a, **k):
		return None


def _pinned_handlers(ip: str):
	"""Handlers that connect to the already-validated `ip` instead of resolving the host
	again (closes the DNS-rebinding window); Host header and TLS SNI keep the hostname."""

	class Conn(http.client.HTTPConnection):
		def connect(self):
			self.sock = socket.create_connection((ip, self.port), self.timeout)

	class SConn(http.client.HTTPSConnection):
		def connect(self):
			sock = socket.create_connection((ip, self.port), self.timeout)
			self.sock = self._context.wrap_socket(sock, server_hostname=self.host)

	class H(urllib.request.HTTPHandler):
		def http_open(self, req):
			return self.do_open(Conn, req)

	class S(urllib.request.HTTPSHandler):
		def https_open(self, req):
			return self.do_open(SConn, req, context=self._context)

	return H(), S()


class _Text(HTMLParser):
	SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.parts: list[str] = []
		self.title = ""
		self._skip = 0
		self._in_title = False

	def handle_starttag(self, tag, attrs):
		if tag == "title":
			self._in_title = True
		if tag in self.SKIP:
			self._skip += 1
		elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"):
			self.parts.append("\n")

	def handle_endtag(self, tag):
		if tag == "title":
			self._in_title = False
		if tag in self.SKIP and self._skip:
			self._skip -= 1

	def handle_data(self, data):
		if self._in_title:
			self.title += data
		elif not self._skip and data.strip():
			self.parts.append(data.strip() + " ")


def _strip_tags(s: str) -> str:
	return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _read_capped(resp, limit: int, deadline: float) -> bytes:
	"""Up to `limit`+1 bytes of the body. A server that trickles bytes forever resets the
	per-read socket timeout each time, so the whole read also gets a deadline."""
	chunks, size = [], 0
	while size <= limit:
		chunk = resp.read1(min(65536, limit + 1 - size))
		if not chunk:
			break
		chunks.append(chunk)
		size += len(chunk)
		if time.monotonic() > deadline:
			raise WebToolError("The page took too long to load.")
	return b"".join(chunks)


def _decode(raw: bytes, content_type: str) -> str:
	charset = re.search(r"charset=([\w-]+)", content_type or "")
	try:
		return raw.decode(charset.group(1) if charset else "utf-8", errors="replace")
	except LookupError:  # a server may declare any name; unknown ones fall back to UTF-8
		return raw.decode("utf-8", errors="replace")


def fetch_url(url: str, *, timeout: int = 15) -> dict:
	"""Fetch a public page as plain text. Redirects are followed manually so every hop is
	re-validated; response size and time are capped. Content is data, never instructions."""
	current = url
	deadline = time.monotonic() + timeout * 2
	for _hop in range(MAX_REDIRECTS + 1):
		ips = assert_public_url(current)
		opener = urllib.request.build_opener(_NoRedirect, *_pinned_handlers(ips[0]))
		req = urllib.request.Request(current, headers={"User-Agent": "ZatGoChatAI/1.0", "Accept": "text/html,text/plain;q=0.9"})
		try:
			resp = opener.open(req, timeout=timeout)
		except urllib.error.HTTPError as exc:
			if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
				current = urllib.parse.urljoin(current, exc.headers["Location"])
				continue
			raise WebToolError(f"The page returned HTTP {exc.code}.") from exc
		except (urllib.error.URLError, OSError) as exc:
			raise WebToolError("The page could not be reached.") from exc
		try:
			with resp:
				ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
				if ctype not in ("text/html", "text/plain", "application/xhtml+xml", ""):
					raise WebToolError(f"Unsupported content type ({ctype}).")
				raw = _read_capped(resp, MAX_FETCH_BYTES, deadline)
		except (OSError, http.client.HTTPException) as exc:  # stalled or broken connection mid-body
			raise WebToolError("The page could not be read.") from exc
		html = _decode(raw[:MAX_FETCH_BYTES], resp.headers.get("Content-Type") or "")
		if ctype == "text/plain":
			text, title = html, ""
		else:
			p = _Text()
			p.feed(html)
			text, title = re.sub(r"\n\s*\n+", "\n\n", "".join(p.parts)).strip(), p.title.strip()
		return {
			"url": current,
			"domain": domain_of(current),
			"title": title,
			"text": text[:MAX_FETCH_CHARS],
			"truncated": len(text) > MAX_FETCH_CHARS or len(raw) > MAX_FETCH_BYTES,
		}
	raise WebToolError("Too many redirects.")
