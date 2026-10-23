"""Outbound HTTP of the admin-defined tool endpoints (REST tools, MCP servers, integration connectors) goes
through core/tool_sources/net.py: http(s) only, a fixed host, no metadata / link-local addresses, no redirects,
capped responses -- and a "read" tool can no longer change data on the other side.

Run: bench --site <site> run-tests --app zatgo_core --module zatgo_core.chat_ai.tests.test_tool_network
Uses a throwaway HTTP server on 127.0.0.1 (loopback is an allowed tool target); no site data is touched."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import TestCase
from unittest.mock import patch

from zatgo_core.chat_ai.core.tool_sources import integrations, mcp, net, rest


class _Handler(BaseHTTPRequestHandler):
	def log_message(self, *args):  # silence
		pass

	def _send(self, status: int, body: bytes, headers: dict | None = None):
		self.send_response(status)
		for k, v in (headers or {}).items():
			self.send_header(k, v)
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)

	def _handle(self):
		length = int(self.headers.get("Content-Length") or 0)
		raw = self.rfile.read(length) if length else b""
		path = self.path.split("?")[0]
		if path == "/redirect":
			return self._send(302, b"", {"Location": "http://169.254.169.254/latest/meta-data/"})
		if path == "/error":
			return self._send(500, b"boom")
		if path == "/big":
			return self._send(200, b"x" * (net.MAX_RESPONSE_BYTES + 10))
		if path == "/rpc":
			return self._send(200, json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "t"}]}}).encode())
		echo = {
			"method": self.command,
			"path": self.path,
			"auth": self.headers.get("Authorization"),
			"body": raw.decode() if raw else "",
		}
		return self._send(200, json.dumps(echo).encode(), {"Content-Type": "application/json"})

	do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _handle


class TestToolNetwork(TestCase):
	@classmethod
	def setUpClass(cls):
		cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
		cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
		threading.Thread(target=cls.server.serve_forever, daemon=True).start()

	@classmethod
	def tearDownClass(cls):
		cls.server.shutdown()
		cls.server.server_close()

	# -- the URL rules ----------------------------------------------------------

	def test_a_template_may_use_placeholders_only_after_the_host(self) -> None:
		net.assert_fixed_host("https://api.example.com/v1/{id}?q={q}")
		net.assert_fixed_host("http://10.0.0.5:8080/x/{a}")
		for bad in (
			"https://{host}/x",
			"https://api.{region}.example.com/x",
			"https://api.example.com:{port}/x",
			"{base}/x",
			"//{host}/x",
		):
			with self.assertRaises(net.ToolNetworkError, msg=bad):
				net.assert_fixed_host(bad)

	def test_only_http_without_credentials(self) -> None:
		for bad in ("file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/", "example.com/x", "http://user:pw@127.0.0.1/"):
			with self.assertRaises(net.ToolNetworkError, msg=bad):
				net.check_url(bad)

	def test_metadata_and_link_local_addresses_are_never_a_tool_target(self) -> None:
		for bad in (
			"http://169.254.169.254/latest/meta-data/",
			"http://[fe80::1]/",
			"http://0.0.0.0/",
			"http://224.0.0.1/",
			"http://[::ffff:169.254.169.254]/",  # IPv4-mapped
			"http://100.100.100.200/",
		):
			with self.assertRaises(net.ToolNetworkError, msg=bad):
				net.check_url(bad)

	def test_a_name_that_resolves_to_a_blocked_address_is_refused(self) -> None:
		infos = [(2, 1, 6, "", ("169.254.169.254", 80)), (2, 1, 6, "", ("93.184.216.34", 80))]
		with patch.object(net.socket, "getaddrinfo", return_value=infos):
			with self.assertRaises(net.ToolNetworkError):
				net.check_url("http://innocent.example.com/")

	def test_private_and_loopback_networks_stay_allowed(self) -> None:
		# An internal service is a legitimate tool; the admin who defines the tool chooses its host.
		self.assertEqual(net.check_url("http://10.1.2.3:8080/x"), ["10.1.2.3"])
		self.assertEqual(net.check_url(self.base + "/ok"), ["127.0.0.1"])

	def test_a_saved_url_is_checked_without_a_lookup(self) -> None:
		net.check_configured_url("")  # optional field
		net.check_configured_url("https://api.example.com/v1/{id}", template=True)
		net.check_configured_url("http://10.0.0.5:9000/mcp")
		for bad, template in (
			("file:///etc/passwd", False),
			("ftp://example.com/x", False),
			("https://user:pw@example.com/x", False),
			("https://{host}/x", True),
			("not a url", False),
		):
			with self.assertRaises(net.ToolNetworkError, msg=bad):
				net.check_configured_url(bad, template=template)

	# -- the request ------------------------------------------------------------

	def test_a_normal_call(self) -> None:
		resp = net.request(self.base + "/echo?a=1", method="POST", headers={"Authorization": "Bearer t"}, body=b"hi")
		self.assertEqual(resp.status, 200)
		echoed = json.loads(resp.text())
		self.assertEqual((echoed["method"], echoed["auth"], echoed["body"]), ("POST", "Bearer t", "hi"))

	def test_a_redirect_is_not_followed(self) -> None:
		with self.assertRaises(net.ToolNetworkError) as ctx:
			net.request(self.base + "/redirect", headers={"Authorization": "Bearer secret"})
		self.assertIn("redirect", str(ctx.exception))

	def test_an_error_status_is_returned_not_raised(self) -> None:
		resp = net.request(self.base + "/error")
		self.assertEqual((resp.status, resp.text()), (500, "boom"))

	def test_a_huge_response_is_refused(self) -> None:
		with self.assertRaises(net.ToolNetworkError):
			net.request(self.base + "/big")

	# -- the tool sources -------------------------------------------------------

	def test_a_rest_tool_calls_its_endpoint_and_words_http_errors(self) -> None:
		handler = rest._make_handler({"method": "GET", "url_template": self.base + "/echo/{id}?v={v}", "auth_type": "None"})
		out = handler(id="a b", v="1")
		self.assertEqual(out["status"], 200)
		self.assertEqual(out["data"]["path"], "/echo/a%20b?v=1")
		failing = rest._make_handler({"method": "GET", "url_template": self.base + "/error", "auth_type": "None"})
		with self.assertRaisesRegex(RuntimeError, "REST 500: boom"):
			failing()

	def test_a_rest_tool_whose_host_is_a_placeholder_never_calls_out(self) -> None:
		handler = rest._make_handler({"method": "GET", "url_template": "https://{host}/x", "auth_type": "None"})
		with patch.object(net, "check_url") as resolve, self.assertRaises(net.ToolNetworkError):
			handler(host="169.254.169.254")
		resolve.assert_not_called()

	def test_a_rest_tool_that_gets_redirected_fails_instead_of_following(self) -> None:
		handler = rest._make_handler({"method": "GET", "url_template": self.base + "/redirect", "auth_type": "None"})
		with self.assertRaises(net.ToolNetworkError):
			handler()

	def test_the_custom_connector_read_tool_cannot_write(self) -> None:
		row = {"name": "abcdefgh12", "label": "T", "base_url": self.base, "auth_type": "Bearer"}
		with patch.object(integrations, "_token", return_value="tok"):
			read, write = integrations._custom_tools(row)
			self.assertEqual((read.category, read.confirmation_required), ("read", False))
			self.assertEqual((write.category, write.confirmation_required), ("write", True))
			self.assertEqual(read.handler(path="/echo")["path"], "/echo")
			self.assertEqual(read.handler(path="/echo")["auth"], "Bearer tok")
			with self.assertRaisesRegex(ValueError, "only does GET, HEAD"):
				read.handler(path="/echo", method="DELETE")
			out = write.handler(path="/echo", method="POST", body={"a": 1})
			self.assertEqual((out["method"], json.loads(out["body"])), ("POST", {"a": 1}))
			with self.assertRaisesRegex(ValueError, "only does POST"):
				write.handler(path="/echo", method="GET")

	def test_an_mcp_tool_is_read_only_only_when_its_server_says_so(self) -> None:
		self.assertTrue(mcp._read_only({"name": "a", "annotations": {"readOnlyHint": True}}))
		for tool in ({"name": "a"}, {"name": "a", "annotations": {}}, {"name": "a", "annotations": {"readOnlyHint": "yes"}}, {"annotations": "x"}):
			self.assertFalse(mcp._read_only(tool), tool)

	def test_mcp_json_rpc_goes_through_the_guarded_client(self) -> None:
		self.assertEqual(mcp._jsonrpc(self.base + "/rpc", "tools/list"), {"tools": [{"name": "t"}]})
		with self.assertRaises(net.ToolNetworkError):
			mcp._jsonrpc("file:///etc/passwd", "tools/list")

	def test_no_tool_source_calls_urlopen_directly(self) -> None:
		import pathlib

		for path in pathlib.Path(net.__file__).parent.glob("*.py"):
			if path.name == "net.py":
				continue
			self.assertNotIn("urlopen", path.read_text(), path.name)
