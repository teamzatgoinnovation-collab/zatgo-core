"""Standard API envelope."""

from __future__ import annotations


def ok(data=None, **extra):
	payload = {"ok": True, "data": data}
	payload.update(extra)
	return payload


def fail(error: str, **extra):
	payload = {"ok": False, "error": error}
	payload.update(extra)
	return payload
