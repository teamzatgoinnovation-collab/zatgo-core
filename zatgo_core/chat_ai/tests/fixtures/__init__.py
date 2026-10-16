"""Real (not mocked) sample files for the workspace tests.

Everything here builds genuine bytes in the format named: DOCX through
python-docx, XLSX through openpyxl, image files through Pillow, and the PDFs are
written by hand (object table and xref offsets computed) so the tests exercise
the same parsers an upload would.
"""

from __future__ import annotations

import io
import zipfile


def make_docx(paragraphs: list[str] | None = None, tables: list[list[list[str]]] | None = None) -> bytes:
	import docx

	d = docx.Document()
	for p in paragraphs or []:
		d.add_paragraph(p)
	for rows in tables or []:
		t = d.add_table(rows=len(rows), cols=len(rows[0]))
		for i, row in enumerate(rows):
			for j, cell in enumerate(row):
				t.cell(i, j).text = cell
	buf = io.BytesIO()
	d.save(buf)
	return buf.getvalue()


def make_xlsx(sheets: dict[str, list[list]]) -> bytes:
	import openpyxl

	wb = openpyxl.Workbook()
	wb.remove(wb.active)
	for name, rows in sheets.items():
		ws = wb.create_sheet(name)
		for row in rows:
			ws.append(row)
	buf = io.BytesIO()
	wb.save(buf)
	return buf.getvalue()


def _pdf_escape(text: str) -> str:
	return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[str]] | list[str]) -> bytes:
	"""A valid PDF 1.4 with one Helvetica text object per page. `pages` is a list of
	pages, each a list of lines (a flat list of strings is one page). ASCII text only."""
	if pages and isinstance(pages[0], str):
		pages = [pages]  # type: ignore[list-item]
	n = len(pages)
	# object numbering: 1 catalog, 2 pages, 3 font, then (page, contents) pairs
	objs: dict[int, bytes] = {
		1: b"<< /Type /Catalog /Pages 2 0 R >>",
		3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
	}
	kids = []
	for i, lines in enumerate(pages):
		page_id, content_id = 4 + 2 * i, 5 + 2 * i
		kids.append(f"{page_id} 0 R")
		body = "BT /F1 12 Tf 14 TL 72 720 Td " + " T* ".join(f"({_pdf_escape(ln)}) Tj" for ln in lines) + " ET"
		stream = body.encode("latin-1")
		objs[content_id] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
		objs[page_id] = (
			f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
			f"/Resources << /Font << /F1 3 0 R >> >> >>"
		).encode()
	objs[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {n} >>".encode()
	out = io.BytesIO()
	out.write(b"%PDF-1.4\n")
	offsets = {}
	for num in sorted(objs):
		offsets[num] = out.tell()
		out.write(f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n")
	xref = out.tell()
	size = max(objs) + 1
	out.write(f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n")
	for num in range(1, size):
		out.write(f"{offsets[num]:010d} 00000 n \n".encode())
	out.write(f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
	return out.getvalue()


def make_blank_pdf(pages: int = 1) -> bytes:
	"""A valid PDF with pages but no text at all (what a scan looks like to a text extractor)."""
	from pypdf import PdfWriter

	w = PdfWriter()
	for _ in range(pages):
		w.add_blank_page(width=200, height=200)
	buf = io.BytesIO()
	w.write(buf)
	return buf.getvalue()


def encrypt_pdf(pdf: bytes, *, user_password: str, owner_password: str | None = None) -> bytes:
	from pypdf import PdfReader, PdfWriter

	w = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
	w.encrypt(user_password=user_password, owner_password=owner_password or user_password, algorithm="AES-128")
	buf = io.BytesIO()
	w.write(buf)
	return buf.getvalue()


def make_image(fmt: str = "PNG", size: tuple[int, int] = (8, 8), *, noise: bool = False) -> bytes:
	"""A real image. `noise=True` makes it incompressible (large files from few pixels)."""
	import os

	from PIL import Image

	w, h = size
	if noise:
		img = Image.frombytes("RGB", size, os.urandom(w * h * 3))
	else:
		img = Image.new("RGB", size)
		img.putdata([(x * 255 // max(w, 1), y * 255 // max(h, 1), 90) for y in range(h) for x in range(w)])
	buf = io.BytesIO()
	img.save(buf, format=fmt)
	return buf.getvalue()


def make_zip_bomb_docx(uncompressed_mb: int = 12) -> bytes:
	"""A ZIP that carries a `word/` entry (so it passes the DOCX magic check) and expands
	far beyond the allowed ratio."""
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
		z.writestr("[Content_Types].xml", "<Types/>")
		z.writestr("word/document.xml", b"0" * (uncompressed_mb * 1024 * 1024))
	return buf.getvalue()


def cp1256_csv(rows: list[list[str]], delimiter: str = ",") -> bytes:
	"""Arabic CSV the way Excel on Arabic Windows saves it."""
	return "\n".join(delimiter.join(r) for r in rows).encode("cp1256") + b"\n"
