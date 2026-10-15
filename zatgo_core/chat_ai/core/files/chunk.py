"""Paragraph-aware text chunking for retrieval."""

from __future__ import annotations

import re


def chunk_text(text: str, *, size: int = 1200, overlap: int = 150) -> list[str]:
	"""Split into ~`size`-char chunks on paragraph/line boundaries, carrying
	`overlap` chars of the previous chunk so answers spanning a boundary survive."""
	text = (text or "").strip()
	if not text:
		return []
	if len(text) <= size:
		return [text]
	units: list[str] = []
	for para in re.split(r"\n{2,}", text):
		para = para.strip()
		if not para:
			continue
		if len(para) <= size:
			units.append(para)
			continue
		for line in para.split("\n"):  # long paragraph: fall back to lines, then hard slices
			line = line.strip()
			while len(line) > size:
				units.append(line[:size])
				line = line[size:]
			if line:
				units.append(line)
	chunks, current = [], ""
	for u in units:
		if current and len(current) + len(u) + 2 > size:
			chunks.append(current)
			current = (current[-overlap:] + "\n" if overlap else "") + u
		else:
			current = f"{current}\n\n{u}" if current else u
	if current:
		chunks.append(current)
	return chunks
