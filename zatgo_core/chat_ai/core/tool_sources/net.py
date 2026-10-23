"""Guarded outbound HTTP for the admin-defined tool endpoints (AI REST Tool, AI MCP Server, AI Integration
Connector). They used to call `urllib.request.urlopen` directly: any scheme (`file://`), any address
(cloud-metadata services), redirects followed to anywhere, unbounded responses.

What this enforces:

- http(s) only, no credentials inside the URL.
- A URL *template* has a fixed host: a `{placeholder}` in the scheme / host / port is refused, so the model
  (which can be talked into things) fills only the path, query and body -- never decides where the request
  (and the stored token) goes.
- Addresses that are never a legitimate tool target are refused: link-local (including the 169.254.169.254
  metadata address), unspecified, multicast, reserved, and the other clouds' metadata addresses. Private and
  loopback networks are allowed: an internal service is a legitimate tool, and the admin who defines the tool
  chooses its host. (Chat AI's *model* endpoints are the ones restricted to the private network:
  providers/local_guard.py.)
- The connection is pinned to the address that was checked (no second DNS lookup between check and connect).
- Redirects are not followed: a 3xx would carry the request, and its Authorization header, to another host.
- The response body and the time are capped.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from zatgo_core.chat_ai.core.web_search import _NoRedirect, _pinned_handlers

MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_TIMEOUT = 60

# Cloud metadata services outside the link-local block (Alibaba, Oracle, AWS IPv6).
_METADATA = {"100.100.100.200", "192.0.0.192", "fd00:ec2::254"}


class ToolNetworkError(RuntimeError):
	"""The endpoint is not allowed, did not answer properly, or answered too much."""


@dataclass
class Response:
	status: int
	body: bytes

	def text(self) -> str:
		return self.body.decode("utf-8", errors="replace")


def assert_fixed_host(template: str) -> None:
	"""A URL template may use {placeholders} in its path and query only."""
	template = template or ""
	m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*:)?//([^/?#]*)", template)
	# "https://api.example.com/v1/{id}": the authority is what follows "//" up to the first "/", "?" or "#"
	head = m.group(0) if m else template.split("/", 1)[0]
	if "{" in head or "}" in head:
		raise ToolNetworkError("The host of a tool URL must be fixed: {placeholders} are allowed only in the path or query.")


def check_configured_url(url: str, *, template: bool = False) -> None:
	"""Save-time check of a URL an admin typed into a tool / server / connector (no DNS lookup): http(s), a host,
	no credentials, and -- for a template -- a fixed host. Empty is fine (the field is optional)."""
	url = (url or "").strip()
	if not url:
		return
	if template:
		assert_fixed_host(url)
	parts = urllib.parse.urlparse(url)
	if parts.scheme not in ("http", "https") or not parts.hostname:
		raise ToolNetworkError("Only http(s) URLs can be called.")
	if parts.username or parts.password:
		raise ToolNetworkError("URLs with credentials are not allowed; use the authentication setting.")


def _blocked(ip: str) -> bool:
	addr = ipaddress.ip_address(ip)
	if addr.version == 6 and addr.ipv4_mapped:
		addr = addr.ipv4_mapped
	return (
		str(addr) in _METADATA
		or addr.is_link_local
		or addr.is_unspecified
		or addr.is_multicast
		or addr.is_reserved
	)


def check_url(url: str) -> list[str]:
	"""Validate `url` and return the addresses it resolves to (for connection pinning)."""
	parts = urllib.parse.urlparse(url or "")
	if parts.scheme not in ("http", "https") or not parts.hostname:
		raise ToolNetworkError("Only http(s) URLs can be called.")
	if parts.username or parts.password:
		raise ToolNetworkError("URLs with credentials are not allowed; use the tool's authentication setting.")
	try:
		port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
	except ValueError as exc:
		raise ToolNetworkError("That port is not allowed.") from exc
	try:
		infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
	except socket.gaierror as exc:
		raise ToolNetworkError("The address could not be resolved.") from exc
	ips = list({i[4][0] for i in infos})
	if not ips or any(_blocked(ip) for ip in ips):
		raise ToolNetworkError("That address is not allowed for a tool.")
	return ips


def request(
	url: str,
	*,
	method: str = "GET",
	headers: dict | None = None,
	body: bytes | None = None,
	timeout: int = DEFAULT_TIMEOUT,
) -> Response:
	"""One guarded request. HTTP error statuses are returned (the caller words its own error); a redirect, a
	disallowed address or an oversized / slow response raises ToolNetworkError."""
	ips = check_url(url)
	opener = urllib.request.build_opener(_NoRedirect, *_pinned_handlers(ips[0]))
	req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
	deadline = time.monotonic() + timeout * 2
	try:
		resp = opener.open(req, timeout=timeout)
	except urllib.error.HTTPError as exc:
		if 300 <= exc.code < 400:
			raise ToolNetworkError(f"The endpoint redirected (HTTP {exc.code}); redirects are not followed.") from exc
		return Response(exc.code, _read(exc, deadline))
	except (urllib.error.URLError, OSError) as exc:
		raise ToolNetworkError(f"The endpoint could not be reached ({getattr(exc, 'reason', exc)}).") from exc
	with resp:
		return Response(resp.status, _read(resp, deadline))


def _read(resp, deadline: float) -> bytes:
	chunks, size = [], 0
	while True:
		chunk = resp.read(65536)
		if not chunk:
			break
		chunks.append(chunk)
		size += len(chunk)
		if size > MAX_RESPONSE_BYTES:
			raise ToolNetworkError("The response is too large.")
		if time.monotonic() > deadline:
			raise ToolNetworkError("The endpoint took too long to answer.")
	return b"".join(chunks)
