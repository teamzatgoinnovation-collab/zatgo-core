"""Shared approval text helpers (no Frappe imports)."""

from __future__ import annotations

_PLAN_OK = frozenset({"ok", "yes", "confirm", "proceed", "continue", "go ahead", "y"})


def is_plan_approval_text(message: str) -> bool:
	text = (message or "").strip().lower()
	return text in _PLAN_OK
