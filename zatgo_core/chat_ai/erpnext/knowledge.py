"""Retrieval over a user's attachments (AI Search Index rows of source_type Attachment).

Always scoped to the owner (and session / chosen attachments) in the query itself;
the index doctype is not readable by chat users, so every read goes through here.
Embeddings are optional: without a configured embedding provider the index is
keyword-only and says so.
"""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe.utils import now_datetime

from zatgo_core.chat_ai.core.files.chunk import chunk_text
from zatgo_core.chat_ai.core.knowledge.rank import hybrid_rank
from zatgo_core.chat_ai.core.providers.errors import ProviderError

EMBED_BATCH = 64
MAX_CANDIDATE_CHUNKS = 5000


def _embedder(settings: dict):
	"""Embedding provider, or None when not configured/supported.

	Opt-in: only when an Embedding Provider is chosen in Chat AI Settings. Having a chat
	API key must not silently start sending every upload to an embeddings endpoint."""
	try:
		from zatgo_core.chat_ai.core.providers.registry import from_settings

		if not settings.get("embedding_provider"):
			return None
		if not (settings.get("embedding_api_key") or settings.get("api_key")):
			return None
		provider = from_settings(settings, for_embedding=True)
		return provider if provider.capabilities.embedding else None
	except Exception:
		return None


def _embed(provider, texts: list[str]) -> list[list[float]] | None:
	if provider is None or not texts:
		return None
	try:
		out: list[list[float]] = []
		for i in range(0, len(texts), EMBED_BATCH):
			out.extend(provider.embed(texts[i : i + EMBED_BATCH]))
		return out if len(out) == len(texts) else None
	except (NotImplementedError, ProviderError, OSError):
		return None
	except Exception:
		frappe.log_error(title="chat_ai embedding failed")
		return None


def delete_attachment_chunks(attachment: str) -> None:
	frappe.db.delete("AI Search Index", {"attachment": attachment, "source_type": "Attachment"})


def index_attachment(attachment: str, text: str, *, session: str, owner: str, settings: dict) -> dict:
	"""(Re)build chunks for one attachment. Returns {chunks, semantic}."""
	delete_attachment_chunks(attachment)
	chunks = chunk_text(text)
	if not chunks:
		return {"chunks": 0, "semantic": False}
	embedder = _embedder(settings)
	vectors = _embed(embedder, chunks)
	model = getattr(embedder, "model", "") if vectors else ""
	now = now_datetime()
	fields = [
		"name", "creation", "modified", "modified_by", "owner", "docstatus", "idx",
		"ref_doctype", "ref_name", "fieldname", "chunk_text", "embedding_json", "model", "checksum",
		"source_type", "attachment", "owner_user", "session", "chunk_index",
	]
	values = []
	for i, chunk in enumerate(chunks):
		values.append(
			(
				frappe.generate_hash(length=10), now, now, owner, owner, 0, 0,
				"AI Attachment", attachment, "extracted_text", chunk,
				json.dumps(vectors[i]) if vectors else "", model,
				hashlib.sha256(f"{attachment}:{i}:{chunk}".encode()).hexdigest(),
				"Attachment", attachment, owner, session, i,
			)
		)
	frappe.db.bulk_insert("AI Search Index", fields, values, ignore_duplicates=True)
	return {"chunks": len(chunks), "semantic": bool(vectors)}


def search(
	query: str,
	*,
	user: str,
	session: str | None = None,
	attachment_ids: list[str] | None = None,
	top_k: int = 6,
	settings: dict | None = None,
) -> list[dict]:
	"""Top chunks for `query` among this user's attachments in the session (or the
	given attachments). Each hit carries its source for citation."""
	filters: dict = {"source_type": "Attachment", "owner_user": user}
	if attachment_ids:
		filters["attachment"] = ("in", attachment_ids)
	elif session:
		filters["session"] = session
	else:
		return []
	rows = frappe.get_all(
		"AI Search Index",
		filters=filters,
		fields=["name", "attachment", "chunk_index", "chunk_text", "embedding_json"],
		limit_page_length=MAX_CANDIDATE_CHUNKS,
		order_by="attachment, chunk_index",
	)
	if not rows:
		return []
	embeddings = [json.loads(r.embedding_json) if r.embedding_json else None for r in rows]
	query_vec = None
	if any(embeddings):
		vecs = _embed(_embedder(settings or {}), [query])
		query_vec = vecs[0] if vecs else None
		if query_vec is None:
			embeddings = [None] * len(rows)  # can't embed the query: keyword only, consistently
	ranked = hybrid_rank(query, [r.chunk_text for r in rows], query_embedding=query_vec, doc_embeddings=embeddings)
	names = {r.attachment for r in rows}
	file_names = dict(
		frappe.get_all("AI Attachment", filters={"name": ("in", list(names))}, fields=["name", "file_name"], as_list=True)
	)
	return [
		{
			"attachment": rows[i].attachment,
			"file_name": file_names.get(rows[i].attachment, ""),
			"chunk_index": rows[i].chunk_index,
			"text": rows[i].chunk_text,
			"score": round(score, 4),
			"retrieval": "hybrid" if query_vec else "keyword",
		}
		for i, score in ranked[: max(1, top_k)]
	]
