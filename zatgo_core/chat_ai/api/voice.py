"""Voice / TTS API — Voicebox (https://github.com/jamiepine/voicebox) + health."""

from __future__ import annotations

import frappe

from zatgo_core.chat_ai.api.response import fail, ok
from zatgo_core.chat_ai.core.voicebox import health as vb_health
from zatgo_core.chat_ai.core.voicebox import list_profiles as vb_list_profiles
from zatgo_core.chat_ai.core.voicebox import settings_from_frappe
from zatgo_core.chat_ai.core.voicebox import speak as vb_speak


def _ensure_user():
	if frappe.session.user == "Guest":
		frappe.throw("Login required", frappe.PermissionError)


@frappe.whitelist()
def health():
	"""Check Voicebox reachability from the ERP server."""
	_ensure_user()
	cfg = settings_from_frappe()
	return ok(vb_health(cfg["voicebox_url"]))


@frappe.whitelist()
def profiles():
	"""List Voicebox voice profiles (server-side)."""
	_ensure_user()
	cfg = settings_from_frappe()
	items = vb_list_profiles(cfg["voicebox_url"])
	return ok({"profiles": items, "base_url": cfg["voicebox_url"]})


@frappe.whitelist()
def speak(text: str | None = None, language: str | None = None):
	"""Synthesize speech via Voicebox and return base64 audio for the Desk player.

	Used when Chat AI Settings → Voicebox via server proxy is enabled, or when
	the browser cannot reach Voicebox directly (CORS / remote Desk).
	"""
	_ensure_user()
	if not text or not str(text).strip():
		return fail("text required")
	cfg = settings_from_frappe()
	result = vb_speak(
		str(text),
		base_url=cfg["voicebox_url"],
		profile=cfg["voicebox_profile"],
		language=language,
		engine=cfg["voicebox_engine"],
	)
	if not result.get("ok"):
		return fail(result.get("error") or "Voicebox speak failed")
	return ok(
		{
			"generation_id": result.get("generation_id"),
			"audio_b64": result.get("audio_b64"),
			"content_type": result.get("content_type") or "audio/wav",
			"audio_url": result.get("audio_url"),
			"engine": "voicebox",
			"source": "https://github.com/jamiepine/voicebox",
		}
	)
