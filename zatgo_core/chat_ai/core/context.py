"""Prompt budget helpers: fit history to a token budget, compact context JSON.

Pure python. Token counts are estimates (no tokenizer dependency): conservative enough to keep a
prompt under a model's window across English and Arabic, not exact.
"""

from __future__ import annotations

import json

CLIP_MARK = "\n…[shortened]…\n"
# Least important first: dropped in this order when the context JSON is over budget.
CONTEXT_DROP_ORDER = (
	"recent_documents", "workspace_context", "route_context", "conversation", "current_form", "entity_memory",
)


def estimate_tokens(text) -> int:
	"""~4 chars/token for ASCII, ~1.8 for everything else (Arabic, CJK), plus per-message overhead."""
	s = str(text or "")
	if not s:
		return 0
	ascii_chars = sum(1 for c in s if ord(c) < 128)
	return int(ascii_chars / 4 + (len(s) - ascii_chars) / 1.8) + 4


def clip_text(text: str, max_tokens: int) -> str:
	"""Keep the head and the tail of an over-long text; the middle is the least useful part."""
	s = str(text or "")
	if estimate_tokens(s) <= max_tokens:
		return s
	chars = max(int(max_tokens * 3), 200)
	head = int(chars * 0.6)
	return s[:head] + CLIP_MARK + s[-(chars - head):]


def fit_history(history, budget_tokens: int, *, max_messages: int = 0, min_keep: int = 2):
	"""Newest messages that fit `budget_tokens` (and `max_messages`, if set).

	Returns (kept, dropped), both chronological; `dropped` is everything older than `kept`.
	The newest `min_keep` messages are always kept, an over-long one is clipped rather than lost.
	"""
	msgs = list(history or [])
	windowed = msgs[-max_messages:] if max_messages and max_messages > 0 else msgs
	older = msgs[: len(msgs) - len(windowed)]
	kept: list[dict] = []
	used = 0
	per_message_cap = max(int(budget_tokens * 0.5), 200)
	for m in reversed(windowed):
		item = dict(m)
		item["content"] = clip_text(item.get("content") or "", per_message_cap)
		tokens = estimate_tokens(item["content"])
		if len(kept) >= min_keep and used + tokens > budget_tokens:
			break
		kept.append(item)
		used += tokens
	kept.reverse()
	return kept, older + windowed[: len(windowed) - len(kept)]


def compact_json(obj, max_chars: int, drop_order=CONTEXT_DROP_ORDER) -> str:
	"""JSON of `obj` within `max_chars`: whole low-priority keys are dropped until it fits, so the
	result is always valid JSON (cutting the string mid-way was not)."""
	data = dict(obj) if isinstance(obj, dict) else obj
	out = json.dumps(data, default=str, ensure_ascii=False)
	if len(out) <= max_chars or not isinstance(data, dict):
		return out if len(out) <= max_chars else json.dumps({"truncated": True})
	for key in drop_order:
		if key in data:
			data.pop(key)
			out = json.dumps(data, default=str, ensure_ascii=False)
			if len(out) <= max_chars:
				return out
	# still too large: keep only short scalar values
	slim = {k: v for k, v in data.items() if len(json.dumps(v, default=str, ensure_ascii=False)) <= max_chars // 4}
	slim["truncated"] = True
	return json.dumps(slim, default=str, ensure_ascii=False)[:max_chars]
