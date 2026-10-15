"""Short-lived confirmation tokens for tool and plan approval."""

from __future__ import annotations

import secrets
import time

import frappe

from zatgo_core.chat_ai.core.approval import is_plan_approval_text

_TOKEN_TTL_SEC = 600  # 10 minutes


def _cache_key(session: str, token: str) -> str:
	return f"chat_ai_confirm:{session}:{token}"


def _owner() -> str:
	return frappe.session.user


def issue_token(session: str, payload: dict) -> str:
	"""Store payload server-side; return an unguessable opaque token bound to
	the issuing user and session."""
	token = secrets.token_urlsafe(24)
	frappe.cache.set_value(
		_cache_key(session, token),
		{"payload": payload, "ts": time.time(), "user": _owner()},
		expires_in_sec=_TOKEN_TTL_SEC,
	)
	return token


def consume_token(session: str, token: str | None, expected_kind: str | None = None) -> dict | None:
	"""Validate and delete token; return stored payload or None."""
	if not token or not session:
		return None
	key = _cache_key(session, token)
	entry = frappe.cache.get_value(key)
	if not entry:
		return None
	if time.time() - float(entry.get("ts") or 0) > _TOKEN_TTL_SEC:
		frappe.cache.delete_value(key)
		return None
	if entry.get("user") != _owner():
		return None
	payload = entry.get("payload") or {}
	if expected_kind and payload.get("kind") != expected_kind:
		return None
	frappe.cache.delete_value(key)
	return payload


__all__ = ["issue_token", "consume_token", "is_plan_approval_text"]
