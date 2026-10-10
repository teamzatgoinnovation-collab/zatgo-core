"""Knowledge Provider SDK stubs (vector work deferred to v0.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Chunk:
	text: str
	source: str = ""
	doctype: str = ""
	name: str = ""
	score: float = 0.0
	metadata: dict = field(default_factory=dict)


@runtime_checkable
class KnowledgeProvider(Protocol):
	name: str

	def search(self, query: str, ctx: dict | None = None) -> list[Chunk]:
		...


_PROVIDERS: dict[str, KnowledgeProvider] = {}


def register_provider(provider: KnowledgeProvider):
	name = getattr(provider, "name", None) or type(provider).__name__
	_PROVIDERS[name] = provider
	return provider


def list_providers() -> list[str]:
	return list(_PROVIDERS.keys())


def search_all(query: str, ctx: dict | None = None, *, limit: int = 20) -> list[Chunk]:
	out: list[Chunk] = []
	for p in _PROVIDERS.values():
		try:
			out.extend(p.search(query, ctx) or [])
		except Exception:
			pass
	out.sort(key=lambda c: c.score, reverse=True)
	return out[:limit]


class DocTypeKnowledgeProvider:
	"""Wraps existing ERP search tools when available — stub for v0.3."""

	name = "doctype"

	def search(self, query: str, ctx: dict | None = None) -> list[Chunk]:
		ctx = ctx or {}
		# Best-effort: use frappe.db if present; otherwise empty
		try:
			import frappe
		except Exception:
			return []
		chunks: list[Chunk] = []
		# Prefer Global Search if enabled later; for now list a few DocTypes by title
		q = (query or "").strip()
		if not q:
			return []
		for dt in ("Customer", "Item", "Project", "Task", "Sales Invoice"):
			if not frappe.db.exists("DocType", dt):
				continue
			if not frappe.has_permission(dt, "read"):
				continue
			try:
				rows = frappe.get_all(
					dt,
					filters=[["name", "like", f"%{q}%"]],
					fields=["name"],
					limit_page_length=5,
				)
				for r in rows:
					chunks.append(
						Chunk(
							text=f"{dt} {r.name}",
							source="doctype",
							doctype=dt,
							name=r.name,
							score=0.5,
						)
					)
			except Exception:
				continue
		return chunks


# Register built-in on import
register_provider(DocTypeKnowledgeProvider())
