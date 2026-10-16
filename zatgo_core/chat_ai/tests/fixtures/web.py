"""Local HTTP servers speaking the real wire formats the web tools and the
embedding client use. Each records the requests it received.

* PageServer: GET routes (web pages, Brave-style JSON, redirects, slow or broken bodies).
* EmbeddingServer: an OpenAI-compatible `/v1/embeddings` endpoint whose vectors come from
  a small concept map, so "semantically near but lexically different" is testable.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Route:
	"""One scripted response. `body` may be bytes or str. `stall` sleeps (seconds) after
	the headers, before the body; `truncate_to` promises len(body) bytes but sends fewer
	and drops the connection; `dribble=(n, interval)` writes the body n bytes at a time with
	`interval` seconds between writes."""

	def __init__(
		self,
		body: bytes | str = b"",
		*,
		status: int = 200,
		ctype: str | None = "text/html; charset=utf-8",
		headers: dict | None = None,
		delay: float = 0,
		stall: float = 0,
		truncate_to: int | None = None,
		dribble: tuple[int, float] | None = None,
	):
		self.body = body.encode() if isinstance(body, str) else body
		self.status, self.ctype, self.headers = status, ctype, headers or {}
		self.delay, self.stall, self.truncate_to, self.dribble = delay, stall, truncate_to, dribble


def redirect(location: str, status: int = 302) -> Route:
	return Route(b"", status=status, ctype=None, headers={"Location": location})


class PageServer:
	def __init__(self, routes: dict[str, Route] | None = None):
		self.routes: dict[str, Route] = dict(routes or {})
		self.requests: list[dict] = []
		outer = self

		class H(BaseHTTPRequestHandler):
			protocol_version = "HTTP/1.1"

			def do_GET(self):
				outer.requests.append({"path": self.path, "headers": dict(self.headers)})
				route = outer.routes.get(self.path.split("?")[0]) or outer.routes.get("*") or Route(b"nope", status=404)
				try:
					if route.delay:
						time.sleep(route.delay)
					self.send_response(route.status)
					if route.ctype:
						self.send_header("Content-Type", route.ctype)
					for k, v in route.headers.items():
						self.send_header(k, v)
					declared = len(route.body)
					self.send_header("Content-Length", str(declared))
					self.send_header("Connection", "close")
					self.end_headers()
					self.wfile.flush()
					if route.stall:
						time.sleep(route.stall)
					body = route.body if route.truncate_to is None else route.body[: route.truncate_to]
					if route.dribble:
						step, interval = route.dribble
						for i in range(0, len(body), step):
							self.wfile.write(body[i : i + step])
							self.wfile.flush()
							time.sleep(interval)
					else:
						self.wfile.write(body)
						self.wfile.flush()
				except (BrokenPipeError, ConnectionResetError):
					pass  # the client stopped reading (size cap, timeout): expected

			def log_message(self, *a):
				pass

		self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
		self.httpd.daemon_threads = True
		self.port = self.httpd.server_port
		threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

	@property
	def url(self) -> str:
		return f"http://127.0.0.1:{self.port}"

	def hostport(self, host: str) -> str:
		"""`host:port` for URLs that name a fake hostname (the tests pin it to loopback)."""
		return f"{host}:{self.port}"

	def stop(self):
		self.httpd.shutdown()
		self.httpd.server_close()


def brave_payload(*results: tuple[str, str, str]) -> bytes:
	"""Brave Search API response body: each result is (title, url, description)."""
	return json.dumps(
		{"type": "search", "web": {"results": [{"title": t, "url": u, "description": d} for t, u, d in results]}}
	).encode()


# concept axes: a word in a group points the vector along that group's axis
CONCEPTS = (
	("dog", "puppy", "canine", "hound"),
	("invoice", "payment", "billing", "receipt"),
	("weather", "rain", "storm", "forecast"),
)


def embed_text(text: str) -> list[float]:
	words = text.lower().replace(",", " ").replace(".", " ").split()
	vec = [0.0] * len(CONCEPTS)
	for w in words:
		for i, group in enumerate(CONCEPTS):
			if w in group:
				vec[i] += 1.0
	if not any(vec):
		vec[0] = vec[1] = vec[2] = 0.01  # no concept: faint, nearly neutral vector
	return vec


class EmbeddingServer:
	"""POST /v1/embeddings -> {"data": [{"embedding": [...]}, ...]} in input order.
	`fail_after` makes calls from that number on (1-based) return HTTP 500."""

	def __init__(self, *, fail_after: int | None = None):
		self.requests: list[dict] = []
		self.fail_after = fail_after
		outer = self

		class H(BaseHTTPRequestHandler):
			def do_POST(self):
				n = int(self.headers.get("Content-Length") or 0)
				body = json.loads(self.rfile.read(n) or b"{}")
				outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
				if outer.fail_after is not None and len(outer.requests) >= outer.fail_after:
					self.send_response(500)
					self.send_header("Content-Type", "application/json")
					self.end_headers()
					self.wfile.write(b'{"error": "boom"}')
					return
				inputs = body.get("input") or []
				inputs = [inputs] if isinstance(inputs, str) else inputs
				payload = json.dumps(
					{"object": "list", "model": body.get("model"), "data": [{"index": i, "embedding": embed_text(t)} for i, t in enumerate(inputs)]}
				).encode()
				self.send_response(200)
				self.send_header("Content-Type", "application/json")
				self.end_headers()
				self.wfile.write(payload)

			def log_message(self, *a):
				pass

		self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
		self.httpd.daemon_threads = True
		self.port = self.httpd.server_port
		threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

	@property
	def url(self) -> str:
		return f"http://127.0.0.1:{self.port}"

	def stop(self):
		self.httpd.shutdown()
		self.httpd.server_close()
