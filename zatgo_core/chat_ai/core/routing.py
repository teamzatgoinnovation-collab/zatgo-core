"""Model selection: manual choice always wins; otherwise route by task.

Slots (Chat AI Settings): default_model = balanced, model_fast, model_reasoning,
model_vision, model_coding. Pure python.
"""

from __future__ import annotations

import re

SLOTS = ("model_fast", "model_reasoning", "model_vision", "model_coding")
_CODE = re.compile(
	r"```|\b(def|class|function|stack ?trace|traceback|exception|regex|sql|query|bug|refactor|compile|python|javascript|typescript|html|css|api endpoint)\b|[{};]\s*$",
	re.I | re.M,
)
_REASON = re.compile(
	r"\b(why|explain|analy[sz]e|compare|trade-?offs?|step[- ]by[- ]step|prove|derive|plan|strategy|evaluate|reconcile|root cause|forecast|optimi[sz]e)\b",
	re.I,
)


def allowed_models(settings: dict) -> list[str]:
	"""Models a user may pick: the configured default and slots (de-duplicated, ordered)."""
	out: list[str] = []
	for key in ("default_model",) + SLOTS + ("fallback_model",):
		m = (settings.get(key) or "").strip()
		if m and m not in out:
			out.append(m)
	return out


def classify(text: str, *, has_images: bool, simple: bool = False) -> str:
	"""Slot name for this task; 'balanced' when nothing special."""
	text = text or ""
	if has_images:
		return "vision"
	if _CODE.search(text):
		return "coding"
	if len(text) > 1500 or _REASON.search(text):
		return "reasoning"
	if simple or len(text) < 100:
		return "fast"
	return "balanced"


def pick_model(settings: dict, text: str, *, has_images: bool, simple: bool = False) -> tuple[str | None, str]:
	"""(model override or None for default, slot). Only when routing is enabled and the
	slot's model is configured; unconfigured slots fall back to the default model."""
	if not settings.get("enable_model_routing"):
		return None, "balanced"
	slot = classify(text, has_images=has_images, simple=simple)
	model = (settings.get(f"model_{slot}") or "").strip() if slot != "balanced" else ""
	return (model or None), slot
