"""Voicebox TTS client — https://github.com/jamiepine/voicebox

Talks to a running Voicebox server (default http://127.0.0.1:17493):
  POST /speak → poll GET /history/{id} → GET /audio/{id}
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_URL = "http://127.0.0.1:17493"
CLIENT_ID = "chat-ai"
# Voicebox SpeakRequest language pattern (no Malayalam)
_VOICEBOX_LANGS = frozenset(
	{
		"zh",
		"en",
		"ja",
		"ko",
		"de",
		"fr",
		"ru",
		"pt",
		"es",
		"it",
		"he",
		"ar",
		"da",
		"el",
		"fi",
		"hi",
		"ms",
		"nl",
		"no",
		"pl",
		"sv",
		"sw",
		"tr",
	}
)


def map_language(code: str | None) -> str:
	c = (code or "en").strip().lower().split("-")[0]
	if c in _VOICEBOX_LANGS:
		return c
	return "en"


def normalize_base_url(url: str | None) -> str:
	base = (url or DEFAULT_URL).strip().rstrip("/")
	return base or DEFAULT_URL


def _request(
	method: str,
	url: str,
	*,
	payload: dict | None = None,
	headers: dict | None = None,
	timeout: float = 30,
) -> tuple[int, Any, bytes]:
	body = None
	hdrs = {"Accept": "application/json", "X-Voicebox-Client-Id": CLIENT_ID}
	if headers:
		hdrs.update(headers)
	if payload is not None:
		body = json.dumps(payload).encode("utf-8")
		hdrs["Content-Type"] = "application/json"
	req = Request(url, data=body, headers=hdrs, method=method.upper())
	try:
		with urlopen(req, timeout=timeout) as resp:
			raw = resp.read()
			ctype = (resp.headers.get("Content-Type") or "").lower()
			data: Any = raw
			if "application/json" in ctype or (raw[:1] in (b"{", b"[")):
				try:
					data = json.loads(raw.decode("utf-8"))
				except Exception:
					data = raw
			return resp.status, data, raw
	except HTTPError as e:
		raw = e.read() if hasattr(e, "read") else b""
		detail = raw.decode("utf-8", errors="replace")[:500]
		try:
			data = json.loads(detail) if detail else {"detail": str(e)}
		except Exception:
			data = {"detail": detail or str(e)}
		return e.code, data, raw
	except URLError as e:
		return 0, {"detail": str(e.reason if hasattr(e, "reason") else e)}, b""


def health(base_url: str | None = None) -> dict:
	base = normalize_base_url(base_url)
	# Prefer /profiles as a lightweight liveness probe (documented public API)
	status, data, _ = _request("GET", f"{base}/profiles", timeout=5)
	ok = status == 200
	return {
		"ok": ok,
		"status": status,
		"base_url": base,
		"detail": None if ok else (data.get("detail") if isinstance(data, dict) else str(data)),
		"source": "https://github.com/jamiepine/voicebox",
	}


def list_profiles(base_url: str | None = None) -> list[dict]:
	base = normalize_base_url(base_url)
	status, data, _ = _request("GET", f"{base}/profiles", timeout=15)
	if status != 200:
		return []
	if isinstance(data, list):
		return data
	if isinstance(data, dict):
		return data.get("items") or data.get("profiles") or []
	return []


def _get_bytes(url: str, *, timeout: float = 60) -> tuple[int, bytes, str]:
	req = Request(url, headers={"X-Voicebox-Client-Id": CLIENT_ID}, method="GET")
	try:
		with urlopen(req, timeout=timeout) as resp:
			return resp.status, resp.read(), resp.headers.get("Content-Type") or "audio/wav"
	except HTTPError as e:
		return e.code, e.read() if hasattr(e, "read") else b"", "application/octet-stream"
	except URLError:
		return 0, b"", ""


def speak(
	text: str,
	*,
	base_url: str | None = None,
	profile: str | None = None,
	language: str | None = None,
	engine: str | None = None,
	timeout_sec: float = 120,
	poll_interval: float = 0.6,
) -> dict:
	"""Generate speech via Voicebox POST /speak and return audio bytes + meta.

	Returns:
	  { ok, generation_id, audio_b64, content_type, error, audio_url }
	"""
	plain = (text or "").strip()
	if not plain:
		return {"ok": False, "error": "empty text"}

	base = normalize_base_url(base_url)
	payload: dict[str, Any] = {"text": plain[:10000], "language": map_language(language)}
	if profile:
		payload["profile"] = profile
	if engine:
		payload["engine"] = engine

	status, data, _ = _request("POST", f"{base}/speak", payload=payload, timeout=60)
	if status not in (200, 201) or not isinstance(data, dict) or not data.get("id"):
		detail = data.get("detail") if isinstance(data, dict) else str(data)
		return {"ok": False, "error": detail or f"speak failed ({status})", "status": status}

	gen_id = data["id"]
	deadline = time.time() + max(5.0, float(timeout_sec))
	last_status = data.get("status") or "generating"

	while time.time() < deadline:
		st, hist, _ = _request("GET", f"{base}/history/{gen_id}", timeout=15)
		if st == 200 and isinstance(hist, dict):
			last_status = hist.get("status") or last_status
			if last_status == "completed":
				break
			if last_status == "failed":
				return {
					"ok": False,
					"error": hist.get("error") or "Voicebox generation failed",
					"generation_id": gen_id,
				}
		elif data.get("status") == "completed" and data.get("audio_path"):
			break
		time.sleep(poll_interval)
	else:
		return {
			"ok": False,
			"error": f"Voicebox timed out (last status: {last_status})",
			"generation_id": gen_id,
		}

	ast, raw, ctype = _get_bytes(f"{base}/audio/{gen_id}", timeout=60)
	if ast != 200 or not raw:
		return {"ok": False, "error": f"audio fetch failed ({ast})", "generation_id": gen_id}

	return {
		"ok": True,
		"generation_id": gen_id,
		"audio_b64": base64.b64encode(raw).decode("ascii"),
		"content_type": ctype if "audio" in str(ctype) else "audio/wav",
		"audio_url": f"{base}/audio/{gen_id}",
		"base_url": base,
	}


def settings_from_frappe() -> dict:
	"""Read Voicebox-related Chat AI Settings (safe defaults)."""
	import frappe

	def _v(field, default=None):
		try:
			val = frappe.db.get_single_value("Chat AI Settings", field)
			return default if val in (None, "") else val
		except Exception:
			return default

	engine = (_v("tts_engine", "Voicebox") or "Voicebox").strip()
	return {
		"tts_engine": engine,
		"voicebox_url": normalize_base_url(_v("voicebox_url", DEFAULT_URL)),
		"voicebox_profile": (_v("voicebox_profile", "") or "").strip() or None,
		"voicebox_engine": (_v("voicebox_engine", "") or "").strip() or None,
		"voicebox_via_server": int(_v("voicebox_via_server", 0) or 0),
	}
