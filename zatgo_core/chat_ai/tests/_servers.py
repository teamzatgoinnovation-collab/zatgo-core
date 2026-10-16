"""Scriptable local HTTP servers for provider tests: real wire formats, no
product-code fakes. Each server records the requests it received."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class ScriptedServer:
	"""Serves `responses` in order: each is (status, content_type, body_bytes | list[bytes])."""

	def __init__(self, responses):
		self.responses = list(responses)
		self.requests: list[dict] = []
		outer = self

		class H(BaseHTTPRequestHandler):
			def do_POST(self):
				n = int(self.headers.get("Content-Length") or 0)
				raw = self.rfile.read(n)
				try:
					body = json.loads(raw or b"{}")
				except ValueError:
					body = {}
				outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
				status, ctype, payload = outer.responses.pop(0) if outer.responses else (500, "text/plain", b"x")
				self.send_response(status)
				self.send_header("Content-Type", ctype)
				self.end_headers()
				for chunk in payload if isinstance(payload, list) else [payload]:
					self.wfile.write(chunk)
					self.wfile.flush()

			def do_GET(self):  # e.g. web search APIs; the query string stays in `path`
				self.rfile.read(int(self.headers.get("Content-Length") or 0))
				outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": {}})
				status, ctype, payload = outer.responses.pop(0) if outer.responses else (500, "text/plain", b"x")
				self.send_response(status)
				self.send_header("Content-Type", ctype)
				self.end_headers()
				for chunk in payload if isinstance(payload, list) else [payload]:
					self.wfile.write(chunk)
					self.wfile.flush()

			def log_message(self, *a):
				pass

		self.httpd = HTTPServer(("127.0.0.1", 0), H)
		self.port = self.httpd.server_port
		threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

	@property
	def url(self) -> str:
		return f"http://127.0.0.1:{self.port}"

	def stop(self):
		self.httpd.shutdown()


def sse(*events: tuple[str | None, dict | str]) -> list[bytes]:
	"""Build SSE frames; each event is (event_name|None, data)."""
	out = []
	for name, data in events:
		text = data if isinstance(data, str) else json.dumps(data)
		out.append((f"event: {name}\n" if name else "").encode() + f"data: {text}\n\n".encode())
	return out
