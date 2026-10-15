"""Hybrid retrieval ranking: keyword (BM25-style) + semantic (cosine). Pure python."""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD = re.compile(r"\w+", re.UNICODE)  # unicode-aware: Arabic works


def tokenize(text: str) -> list[str]:
	return [t for t in _WORD.findall((text or "").lower()) if len(t) > 1 or t.isdigit()]


def cosine(a: list[float], b: list[float]) -> float:
	if not a or not b or len(a) != len(b):
		return 0.0
	dot = sum(x * y for x, y in zip(a, b))
	na = math.sqrt(sum(x * x for x in a))
	nb = math.sqrt(sum(y * y for y in b))
	return dot / (na * nb) if na and nb else 0.0


def keyword_scores(query: str, docs: list[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
	"""BM25 of `query` against each doc, scaled to 0..1 by the best score."""
	q_terms = set(tokenize(query))
	toks = [tokenize(d) for d in docs]
	if not q_terms or not toks:
		return [0.0] * len(docs)
	n = len(docs)
	avg = (sum(len(t) for t in toks) / n) or 1.0
	df = Counter(term for t in toks for term in q_terms.intersection(t))
	scores = []
	for t in toks:
		tf = Counter(t)
		s = 0.0
		for term in q_terms:
			if not tf[term]:
				continue
			idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
			s += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(t) / avg))
		scores.append(s)
	top = max(scores)
	return [s / top if top > 0 else 0.0 for s in scores]


def hybrid_rank(
	query: str,
	docs: list[str],
	*,
	query_embedding: list[float] | None = None,
	doc_embeddings: list[list[float] | None] | None = None,
	weight_semantic: float = 0.6,
	min_score: float = 0.05,
) -> list[tuple[int, float]]:
	"""[(doc index, score)] best first. Semantic is used only for docs that have an
	embedding; with none available this is plain keyword search."""
	kw = keyword_scores(query, docs)
	out = []
	for i, k in enumerate(kw):
		emb = doc_embeddings[i] if doc_embeddings else None
		if query_embedding and emb:
			sem = max(0.0, cosine(query_embedding, emb))
			score = weight_semantic * sem + (1 - weight_semantic) * k
		else:
			score = k
		if score >= min_score:
			out.append((i, score))
	out.sort(key=lambda p: p[1], reverse=True)
	return out
