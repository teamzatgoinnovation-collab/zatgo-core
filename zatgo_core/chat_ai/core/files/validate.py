"""Upload validation. The client's MIME type and filename are never trusted:
the extension picks the kind, magic bytes must agree, and the stored name is
sanitised (no path components, no control characters)."""

from __future__ import annotations

import os
import re
import unicodedata

# extension -> (kind, server-assigned mime type)
ALLOWED: dict[str, tuple[str, str]] = {
	".pdf": ("document", "application/pdf"),
	".docx": ("document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
	".xlsx": ("spreadsheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
	".csv": ("spreadsheet", "text/csv"),
	".txt": ("text", "text/plain"),
	".md": ("text", "text/markdown"),
	".png": ("image", "image/png"),
	".jpg": ("image", "image/jpeg"),
	".jpeg": ("image", "image/jpeg"),
	".gif": ("image", "image/gif"),
	".webp": ("image", "image/webp"),
}

IMAGE_EXTS = {e for e, (k, _m) in ALLOWED.items() if k == "image"}


class UploadError(ValueError):
	"""User-facing rejection; `code` is stable for clients."""

	def __init__(self, message: str, code: str = "invalid_file"):
		super().__init__(message)
		self.code = code


def safe_filename(name: str | None) -> str:
	# Fold compatibility forms first: NFKC turns fullwidth slashes (U+FF0F, U+FF3C) into real
	# path separators, which must be dropped along with the rest of the path.
	name = unicodedata.normalize("NFKC", name or "")
	name = name.replace("\\", "/").split("/")[-1]  # drop any path
	name = "".join(" " if ch.isspace() else ch for ch in name)  # tabs / newlines separate words; they must not glue them together
	name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
	name = re.sub(r"\s+", " ", name).strip(" .")
	if len(name) > 120:
		stem, ext = os.path.splitext(name)
		name = stem[: 120 - len(ext)] + ext
	return name


def _looks_like_text(content: bytes) -> bool:
	"""No NUL bytes and almost no control characters. Not limited to UTF-8:
	Windows-1256 / Latin-1 CSV exports are legitimate and are decoded later."""
	sample = content[:65536]
	if b"\x00" in sample:
		return False
	controls = sum(1 for b in sample if b < 32 and b not in (9, 10, 13, 12))
	return controls <= max(2, len(sample) // 50)


def _magic_ok(ext: str, content: bytes) -> bool:
	head = content[:16]
	if ext == ".pdf":
		return content[:1024].lstrip().startswith(b"%PDF-")
	if ext in (".docx", ".xlsx"):
		if not head.startswith(b"PK\x03\x04"):
			return False
		marker = b"word/" if ext == ".docx" else b"xl/"
		return marker in content[: 1 << 20] or marker in content[-(1 << 16) :]
	if ext == ".png":
		return head.startswith(b"\x89PNG\r\n\x1a\n")
	if ext in (".jpg", ".jpeg"):
		return head.startswith(b"\xff\xd8\xff")
	if ext == ".gif":
		return head[:6] in (b"GIF87a", b"GIF89a")
	if ext == ".webp":
		return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
	return _looks_like_text(content)  # txt / md / csv


def validate_upload(filename: str | None, content: bytes, *, max_bytes: int) -> tuple[str, str, str]:
	"""Return (safe_filename, kind, mime). Raises UploadError."""
	if not content:
		raise UploadError("The file is empty.", "empty")
	if len(content) > max_bytes:
		raise UploadError(f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.", "too_large")
	safe = safe_filename(filename)
	ext = os.path.splitext(safe)[1].lower()
	if not safe or ext not in ALLOWED:
		raise UploadError(
			"This file type is not supported. Use PDF, DOCX, XLSX, CSV, TXT, Markdown or an image (PNG, JPG, GIF, WebP).",
			"unsupported_type",
		)
	if not _magic_ok(ext, content):
		raise UploadError("The file content does not match its type.", "content_mismatch")
	kind, mime = ALLOWED[ext]
	return safe, kind, mime
