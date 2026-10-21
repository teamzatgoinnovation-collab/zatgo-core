"""Workspace building blocks: upload validation, text extraction, chunking, table
analysis, the calculator, hybrid ranking, model routing and web search / fetch.

These are the pure modules (no DB). Files are real documents built by
`tests/fixtures`, and the web tools run against real local HTTP servers.

Run: bench --site <site> run-tests --app zatgo_core --module zatgo_core.chat_ai.tests.test_workspace
"""

from __future__ import annotations

import inspect
import io
import json
import math
import socket
import sys
import zipfile
import time
import unittest
import urllib.parse
from unittest import mock

from zatgo_core.chat_ai.core import calc, routing, web_search as ws
from zatgo_core.chat_ai.core.files import chunk, extract, table
from zatgo_core.chat_ai.core.files.validate import ALLOWED, UploadError, safe_filename, validate_upload
from zatgo_core.chat_ai.core.knowledge import rank
from zatgo_core.chat_ai.core.providers.errors import ProviderError
from zatgo_core.chat_ai.tests import fixtures as fx
from zatgo_core.chat_ai.tests.fixtures.web import PageServer, Route, brave_payload, redirect

MB = 1024 * 1024


def _code(exc_ctx) -> str:
	return exc_ctx.exception.code


# ---------------------------------------------------------------------------
# validate.py
# ---------------------------------------------------------------------------


class TestValidate(unittest.TestCase):
	def samples(self) -> dict[str, bytes]:
		return {
			"report.pdf": fx.make_pdf(["hello"]),
			"memo.docx": fx.make_docx(["hello"]),
			"book.xlsx": fx.make_xlsx({"S": [["a", 1]]}),
			"data.csv": b"a,b\n1,2\n",
			"notes.txt": "plain notes\n".encode(),
			"readme.md": b"# Title\n\ntext\n",
			"pic.png": fx.make_image("PNG"),
			"photo.jpg": fx.make_image("JPEG"),
			"photo2.jpeg": fx.make_image("JPEG"),
			"anim.gif": fx.make_image("GIF"),
			"modern.webp": fx.make_image("WEBP"),
		}

	def test_every_allowed_type_is_accepted_with_server_assigned_mime(self):
		samples = self.samples()
		covered = {"." + n.rsplit(".", 1)[1] for n in samples}
		self.assertEqual(covered, set(ALLOWED), "a type was added to ALLOWED without a test file")
		for name, content in samples.items():
			with self.subTest(name):
				safe, kind, mime = validate_upload(name, content, max_bytes=MB)
				ext = "." + name.rsplit(".", 1)[1]
				self.assertEqual((safe, kind, mime), (name, ALLOWED[ext][0], ALLOWED[ext][1]))

	def test_client_extension_case_is_normalised_but_name_kept(self):
		safe, kind, _ = validate_upload("Quarterly.PDF", fx.make_pdf(["x"]), max_bytes=MB)
		self.assertEqual((safe, kind), ("Quarterly.PDF", "document"))

	def test_executable_renamed_to_allowed_type_is_rejected(self):
		exe = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64
		elf = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64
		for name in ("invoice.pdf", "logo.png", "logo.jpg", "logo.gif", "logo.webp", "doc.docx", "sheet.xlsx", "notes.txt", "d.csv"):
			for blob in (exe, elf):
				with self.subTest(name=name, head=blob[:2]):
					with self.assertRaises(UploadError) as c:
						validate_upload(name, blob, max_bytes=MB)
					self.assertEqual(_code(c), "content_mismatch")

	def test_office_files_must_carry_their_own_package_marker(self):
		xlsx, docx = fx.make_xlsx({"S": [[1]]}), fx.make_docx(["x"])
		for name, content in (("a.docx", xlsx), ("a.xlsx", docx), ("a.docx", b"PK\x03\x04" + b"\x00" * 50)):
			with self.subTest(name=name):
				with self.assertRaises(UploadError) as c:
					validate_upload(name, content, max_bytes=MB)
				self.assertEqual(_code(c), "content_mismatch")

	def test_image_signatures_are_not_interchangeable(self):
		png, jpg = fx.make_image("PNG"), fx.make_image("JPEG")
		for name, content in (("a.png", jpg), ("a.jpg", png), ("a.gif", png), ("a.webp", jpg)):
			with self.subTest(name=name):
				with self.assertRaises(UploadError) as c:
					validate_upload(name, content, max_bytes=MB)
				self.assertEqual(_code(c), "content_mismatch")

	def test_unsupported_extensions(self):
		for name in ("a.exe", "a.svg", "a.html", "a.htm", "a.js", "a.php", "a.sh", "a.bat", "a.zip", "a.doc", "a.xls", "a.pdf.exe", "README", ".pdf", "a.", "a.pdf ", "noext"):
			with self.subTest(name):
				try:
					validate_upload(name, b"<svg/>", max_bytes=MB)
				except UploadError as exc:
					# "a.pdf " loses its trailing space and then fails on content, which is also a rejection
					self.assertIn(exc.code, ("unsupported_type", "content_mismatch"))
				else:
					self.fail(f"{name!r} was accepted")

	def test_svg_and_html_are_rejected_even_with_an_allowed_looking_name(self):
		for name, body in (("pic.png", b"<svg onload=alert(1)>"), ("page.txt.html", b"<script>x</script>"), ("x.html", b"<html></html>")):
			with self.assertRaises(UploadError):
				validate_upload(name, body, max_bytes=MB)

	def test_text_sniffing(self):
		with self.assertRaises(UploadError) as c:  # NUL byte: binary
			validate_upload("a.txt", b"hello\x00world", max_bytes=MB)
		self.assertEqual(_code(c), "content_mismatch")
		with self.assertRaises(UploadError):  # control-character soup
			validate_upload("a.csv", bytes(range(1, 9)) * 400, max_bytes=MB)
		validate_upload("a.txt", "سلام\r\nمرحبا\ttab\n".encode(), max_bytes=MB)  # UTF-8 Arabic, CRLF, tabs

	def test_windows_1256_arabic_csv_is_accepted_and_readable(self):
		rows = [["الاسم", "المبلغ"], ["أحمد", "100"], ["فاطمة", "250"]]
		raw = fx.cp1256_csv(rows)
		with self.assertRaises(UnicodeDecodeError):
			raw.decode("utf-8")
		safe, kind, mime = validate_upload("sales.csv", raw, max_bytes=MB)
		self.assertEqual((safe, kind, mime), ("sales.csv", "spreadsheet", "text/csv"))
		self.assertIn("أحمد", extract.extract_text("sales.csv", raw).text)

	def test_path_components_are_dropped(self):
		for given, expected in (
			("../../etc/passwd.txt", "passwd.txt"),
			("/etc/passwd.txt", "passwd.txt"),
			("..\\..\\windows\\system32\\evil.txt", "evil.txt"),
			("C:\\Users\\me\\report.csv", "report.csv"),
			("a/b/c/d.md", "d.md"),
			("./.hidden/x.txt", "x.txt"),
		):
			with self.subTest(given):
				self.assertEqual(safe_filename(given), expected)
				safe, _k, _m = validate_upload(given, b"text\n", max_bytes=MB)
				self.assertEqual(safe, expected)

	def test_null_bytes_and_control_characters_are_removed(self):
		self.assertEqual(safe_filename("re\x00port.txt"), "report.txt")
		self.assertEqual(safe_filename("a\nb\r\tc.txt"), "a b c.txt")
		# a NUL cannot smuggle a second extension past the checks: the result is judged as a whole
		with self.assertRaises(UploadError) as c:
			validate_upload("invoice.pdf\x00.exe", fx.make_pdf(["x"]), max_bytes=MB)
		self.assertEqual(_code(c), "unsupported_type")

	def test_unicode_tricks_cannot_reintroduce_path_separators(self):
		fullwidth_slash, fullwidth_backslash = "\uff0f", "\uff3c"
		for given in (
			f"..{fullwidth_slash}..{fullwidth_slash}etc{fullwidth_slash}passwd.txt",
			f"..{fullwidth_backslash}..{fullwidth_backslash}etc{fullwidth_backslash}passwd.txt",
			f"{fullwidth_slash}etc{fullwidth_slash}passwd.txt",
		):
			with self.subTest(repr(given)):
				safe = safe_filename(given)
				self.assertNotIn("/", safe)
				self.assertNotIn("\\", safe)
				self.assertFalse(safe.startswith("."))
				self.assertEqual(safe, "passwd.txt")

	def test_unicode_tricks_cannot_disguise_the_extension(self):
		# right-to-left override: "invoice<RLO>fdp.exe" renders as "invoiceexe.pdf"
		self.assertEqual(safe_filename("invoice\u202efdp.exe"), "invoicefdp.exe")
		with self.assertRaises(UploadError) as c:
			validate_upload("invoice\u202efdp.exe", fx.make_pdf(["x"]), max_bytes=MB)
		self.assertEqual(_code(c), "unsupported_type")
		self.assertEqual(safe_filename("zero\u200bwidth\u200d.txt"), "zerowidth.txt")  # zero-width characters dropped
		self.assertEqual(safe_filename("ﬁle①.txt"), "file1.txt")  # compatibility forms folded (NFKC)
		self.assertEqual(safe_filename("a\u2024txt"), "a.txt")  # one-dot-leader becomes a real dot, then is judged

	def test_filename_punctuation_that_breaks_shells_and_browsers_is_removed(self):
		self.assertEqual(safe_filename('we<ird>:"na|me?*.txt'), "weirdname.txt")
		self.assertEqual(safe_filename("   ...spaced   out...  .txt"), "spaced out... .txt")

	def test_overlong_names_are_cut_but_keep_their_extension(self):
		name = "a" * 400 + ".pdf"
		safe = safe_filename(name)
		self.assertLessEqual(len(safe), 120)
		self.assertTrue(safe.endswith(".pdf"))
		self.assertEqual(validate_upload(name, fx.make_pdf(["x"]), max_bytes=MB)[0], safe)
		arabic = "ف" * 300 + ".csv"
		self.assertLessEqual(len(safe_filename(arabic)), 120)
		self.assertTrue(safe_filename(arabic).endswith(".csv"))

	def test_missing_or_empty_filename(self):
		for name in (None, "", "   ", "...", "/", "\\"):
			with self.subTest(repr(name)):
				with self.assertRaises(UploadError) as c:
					validate_upload(name, b"text", max_bytes=MB)
				self.assertEqual(_code(c), "unsupported_type")

	def test_empty_and_oversized(self):
		with self.assertRaises(UploadError) as c:
			validate_upload("a.txt", b"", max_bytes=MB)
		self.assertEqual(_code(c), "empty")
		with self.assertRaises(UploadError) as c:
			validate_upload("a.txt", b"x" * 11, max_bytes=10)
		self.assertEqual(_code(c), "too_large")
		self.assertIn("MB", str(c.exception))
		self.assertEqual(validate_upload("a.txt", b"x" * 10, max_bytes=10)[0], "a.txt")  # exactly at the limit
		# size is judged before type, so a huge disallowed file is "too large" and never inspected
		with self.assertRaises(UploadError) as c:
			validate_upload("a.exe", b"x" * 11, max_bytes=10)
		self.assertEqual(_code(c), "too_large")


# ---------------------------------------------------------------------------
# extract.py
# ---------------------------------------------------------------------------


class TestExtract(unittest.TestCase):
	def test_pdf_text_pages_and_order(self):
		pdf = fx.make_pdf([["Invoice 1001", "Total due 500 SAR"], ["Second page body"]])
		out = extract.extract_pdf(pdf)
		self.assertEqual(out.pages, 2)
		self.assertFalse(out.truncated)
		self.assertIn("[Page 1]\nInvoice 1001", out.text)
		self.assertIn("Total due 500 SAR", out.text)
		self.assertLess(out.text.index("[Page 1]"), out.text.index("[Page 2]"))
		self.assertIn("Second page body", out.text.split("[Page 2]")[1])

	def test_pdf_page_cap_marks_truncation(self):
		pdf = fx.make_pdf([["page one"], ["page two"], ["page three"]])
		with mock.patch.object(extract, "MAX_PDF_PAGES", 2):
			out = extract.extract_pdf(pdf)
		self.assertTrue(out.truncated)
		self.assertEqual(out.pages, 3)
		self.assertIn("page two", out.text)
		self.assertNotIn("page three", out.text)

	def test_password_protected_pdf(self):
		locked = fx.encrypt_pdf(fx.make_pdf(["secret"]), user_password="s3cret")
		with self.assertRaisesRegex(extract.ExtractError, "password protected"):
			extract.extract_pdf(locked)

	def test_pdf_with_only_an_owner_password_opens_like_any_reader_would(self):
		# Restricts printing/copying but needs no password to read: must not be refused as "password protected".
		restricted = fx.encrypt_pdf(fx.make_pdf(["open to all readers"]), user_password="", owner_password="owner-only")
		self.assertIn("open to all readers", extract.extract_pdf(restricted).text)

	def test_scanned_pdf_without_text_layer_gives_actionable_error(self):
		with self.assertRaisesRegex(extract.ExtractError, "no extractable text.*image"):
			extract.extract_pdf(fx.make_blank_pdf(pages=2))

	def test_corrupt_pdfs_fail_with_a_safe_message(self):
		good = fx.make_pdf(["hello"])
		for label, blob in (("garbage", b"%PDF-1.4\nnot really a pdf"), ("truncated", good[: len(good) // 2]), ("header only", b"%PDF-1.7")):
			with self.subTest(label):
				with self.assertRaises(extract.ExtractError) as c:
					extract.extract_pdf(blob)
				self.assertEqual(str(c.exception), "The PDF could not be read.")

	def test_docx_paragraphs_and_tables(self):
		doc = fx.make_docx(
			["First paragraph", "", "مرحبا بالعالم"],
			tables=[[["Item", "Qty"], ["Widget", "4"], ["", ""]]],
		)
		lines = extract.extract_docx(doc).text.split("\n")
		self.assertEqual(lines, ["First paragraph", "مرحبا بالعالم", "Item | Qty", "Widget | 4"])  # blank paragraph and empty row dropped

	def test_docx_without_text_and_corrupt_docx(self):
		with self.assertRaisesRegex(extract.ExtractError, "no text"):
			extract.extract_docx(fx.make_docx([]))
		with self.assertRaises(extract.ExtractError):
			extract.extract_docx(b"this is not a zip")
		buf = io.BytesIO()
		with zipfile.ZipFile(buf, "w") as z:
			z.writestr("word/document.xml", "<broken")  # right marker, broken package
		with self.assertRaises(extract.ExtractError) as c:
			extract.extract_docx(buf.getvalue())
		self.assertNotIn("Traceback", str(c.exception))

	def test_xlsx_multiple_sheets_and_empty_sheet(self):
		book = fx.make_xlsx(
			{
				"Sales": [["Region", "Amount"], ["North", 100], ["South", 250.5]],
				"Empty": [],
				"Notes": [["note"], ["مرحبا"]],
			}
		)
		out = extract.extract_xlsx(book)
		self.assertIn("[Sheet: Sales]\nRegion,Amount\nNorth,100\nSouth,250.5", out.text)
		self.assertIn("[Sheet: Notes]\nnote\nمرحبا", out.text)
		self.assertNotIn("[Sheet: Empty]", out.text)
		self.assertEqual(out.pages, 3)

	def test_xlsx_all_empty_or_corrupt(self):
		with self.assertRaisesRegex(extract.ExtractError, "empty"):
			extract.extract_xlsx(fx.make_xlsx({"A": [], "B": [[None, None]]}))
		with self.assertRaises(extract.ExtractError):
			extract.extract_xlsx(b"PK\x03\x04 nonsense")

	def test_xlsx_row_cap(self):
		book = fx.make_xlsx({"S": [["n"]] + [[i] for i in range(50)]})
		(name, rows), = extract.read_xlsx_rows(book, max_rows=10)
		self.assertEqual((name, len(rows)), ("S", 10))

	def test_plain_text_decoding(self):
		self.assertEqual(extract.extract_text("a.txt", "\ufeffhello".encode("utf-8")).text, "hello")  # BOM dropped
		self.assertEqual(extract.extract_text("a.md", "# عنوان".encode()).text, "# عنوان")
		raw = fx.cp1256_csv([["الاسم", "المبلغ"], ["أحمد", "100"]])
		self.assertIn("أحمد,100", extract.extract_text("a.CSV", raw).text)
		with self.assertRaisesRegex(extract.ExtractError, "empty"):
			extract.extract_text("a.txt", b"  \n\t ")
		with self.assertRaisesRegex(extract.ExtractError, "no text"):
			extract.extract_text("a.png", b"x")

	def test_text_is_truncated_at_max_chars(self):
		text = ("0123456789" * 100_001)[: extract.MAX_CHARS + 500]
		out = extract.extract_text("big.txt", text.encode())
		self.assertTrue(out.truncated)
		self.assertEqual(len(out.text), extract.MAX_CHARS)
		small = extract.extract_text("ok.txt", b"short")
		self.assertFalse(small.truncated)

	def test_zip_bomb_is_rejected_before_parsing(self):
		bomb = fx.make_zip_bomb_docx(uncompressed_mb=12)
		self.assertLess(len(bomb), 100_000)  # tiny on disk, 12 MB when expanded
		with self.assertRaisesRegex(extract.ExtractError, "unsafe size"):
			extract.extract_docx(bomb)
		with self.assertRaisesRegex(extract.ExtractError, "unsafe size"):
			extract.extract_xlsx(bomb)
		with self.assertRaisesRegex(extract.ExtractError, "unsafe size"):
			extract.parse_table("x.xlsx", bomb)

	def test_absolute_expansion_cap(self):
		doc = fx.make_docx(["hello world " * 200])
		with mock.patch.object(extract, "MAX_ZIP_UNCOMPRESSED", 100):
			with self.assertRaisesRegex(extract.ExtractError, "unsafe size"):
				extract.extract_docx(doc)
		extract.extract_docx(doc)  # an ordinary document is unaffected

	def test_parse_table_delimiters(self):
		for delim in (",", ";", "\t", "|"):
			with self.subTest(repr(delim)):
				raw = delim.join(["name", "amount", "city"]) + "\n" + delim.join(["Ann", "10", "Riyadh"]) + "\n" + delim.join(["Bob", "20", "Jeddah"]) + "\n"
				cols, rows = extract.parse_table("t.csv", raw.encode())
				self.assertEqual(cols, ["name", "amount", "city"])
				self.assertEqual(rows, [["Ann", "10", "Riyadh"], ["Bob", "20", "Jeddah"]])

	def test_parse_table_quotes_arabic_ragged_and_blank_headers(self):
		cols, rows = extract.parse_table("t.csv", b'name,note,\n"Doe, John","said ""hi""",x\nshort\n')
		self.assertEqual(cols, ["name", "note", "column_3"])
		self.assertEqual(rows, [["Doe, John", 'said "hi"', "x"], ["short", "", ""]])
		cols, rows = extract.parse_table("a.csv", fx.cp1256_csv([["الاسم", "المبلغ"], ["أحمد", "100"]], delimiter=";"))
		self.assertEqual((cols, rows), (["الاسم", "المبلغ"], [["أحمد", "100"]]))

	def test_parse_table_xlsx_first_non_empty_sheet_and_row_cap(self):
		book = fx.make_xlsx({"Blank": [], "Data": [["k", "v"]] + [[f"r{i}", i] for i in range(30)]})
		cols, rows = extract.parse_table("d.xlsx", book, max_rows=5)
		self.assertEqual(cols, ["k", "v"])
		self.assertEqual(len(rows), 5)
		self.assertEqual(rows[0], ["r0", 0])

	def test_parse_table_rejects_other_types_and_empty(self):
		with self.assertRaisesRegex(extract.ExtractError, "CSV and XLSX"):
			extract.parse_table("a.txt", b"x")
		with self.assertRaisesRegex(extract.ExtractError, "empty"):
			extract.parse_table("a.csv", b"")


# ---------------------------------------------------------------------------
# chunk.py
# ---------------------------------------------------------------------------


class TestChunk(unittest.TestCase):
	def test_empty_and_short(self):
		for t in (None, "", "   \n\n  "):
			self.assertEqual(chunk.chunk_text(t), [])
		self.assertEqual(chunk.chunk_text("  one small paragraph  "), ["one small paragraph"])

	def test_size_overlap_and_coverage(self):
		paras = [f"Paragraph {i}: " + ("word " * 40).strip() for i in range(40)]
		text = "\n\n".join(paras)
		size, overlap = 500, 80
		chunks = chunk.chunk_text(text, size=size, overlap=overlap)
		self.assertGreater(len(chunks), 3)
		for c in chunks:
			self.assertTrue(c.strip())
			self.assertLessEqual(len(c), size + overlap + 1)
		for prev, nxt in zip(chunks, chunks[1:]):
			self.assertTrue(nxt.startswith(prev[-overlap:]), "next chunk must open with the previous chunk's tail")
		joined = "\n".join(chunks)
		for p in paras:
			self.assertIn(p, joined, "every paragraph survives intact in some chunk")

	def test_no_overlap(self):
		text = "\n\n".join(f"P{i} " + "x" * 90 for i in range(30))
		chunks = chunk.chunk_text(text, size=300, overlap=0)
		for c in chunks:
			self.assertLessEqual(len(c), 300)
		self.assertEqual("\n\n".join(chunks), text)

	def test_huge_single_line_is_hard_sliced_without_loss(self):
		line = "".join(chr(ord("a") + i % 26) for i in range(10_000))
		chunks = chunk.chunk_text(line, size=1200, overlap=150)
		self.assertEqual(len(chunks), 9)
		self.assertEqual(chunks[0], line[:1200])
		rebuilt = chunks[0] + "".join(c[151:] for c in chunks[1:])  # drop "tail + newline" prefix
		self.assertEqual(rebuilt, line)

	def test_long_paragraph_splits_on_lines_first(self):
		lines = [f"row {i}: " + "y" * 60 for i in range(60)]
		chunks = chunk.chunk_text("\n".join(lines), size=400, overlap=0)
		self.assertGreater(len(chunks), 5)
		for c in chunks:
			for part in c.split("\n"):
				self.assertTrue(part == "" or part.startswith("row "), "no line was cut in half")

	def test_arabic_text(self):
		text = "\n\n".join("فقرة رقم %d " % i + "كلمة " * 50 for i in range(20))
		chunks = chunk.chunk_text(text, size=400, overlap=40)
		self.assertGreater(len(chunks), 3)
		self.assertTrue(all("فقرة" in c or "كلمة" in c for c in chunks))


# ---------------------------------------------------------------------------
# table.py
# ---------------------------------------------------------------------------

COLS = ["Region", "Product", "Amount", "Qty"]
ROWS = [
	["North", "A", "100", "1"],
	["North", "B", "250.50", "2"],
	["South", "A", "(50)", "3"],
	["South", "B", "SAR 1,000", "4"],
	["East", "A", "", "5"],
	["East", "C", "٣٠٫٥", "6"],
]


class TestToNumber(unittest.TestCase):
	def test_accepted_forms(self):
		cases = {
			"1,234.50": 1234.5, "1234": 1234.0, "-5": -5.0, "+5": 5.0, "(12)": -12.0, "(1,234.50)": -1234.5,
			"SAR 99": 99.0, "99 SAR": 99.0, "$1,000": 1000.0, "-$5": -5.0, "$-5": -5.0, "SAR -5": -5.0,
			"€ 5.5": 5.5, "12%": 12.0, "1e3": 1000.0, "2.5E-1": 0.25, ".5": 0.5, "  42  ": 42.0,
			"٣٤٫٥": 34.5, "١٢٬٣٤٥": 12345.0, "٠": 0.0, "ر.س 100": 100.0, "1,000,000": 1000000.0,
			"\u22125": -5.0, "5kg": 5.0, "10 pcs": 10.0, "(SAR 12)": -12.0,
			"$.5": 0.5, "-.5": -0.5, "SAR .75": 0.75, "S.R. 20": 20.0, "5.": 5.0,
		}
		for given, expected in cases.items():
			with self.subTest(given):
				self.assertEqual(table.to_number(given), expected)

	def test_numbers_pass_through_and_bools_do_not(self):
		self.assertEqual(table.to_number(5), 5.0)
		self.assertEqual(table.to_number(2.5), 2.5)
		self.assertIsNone(table.to_number(True))
		self.assertIsNone(table.to_number(False))

	def test_non_numbers(self):
		for given in ("", "  ", "abc", None, "N/A", "None", "-", "(", "1.2.3", "1,2,3", "12 34", "e5", "--5"):
			with self.subTest(repr(given)):
				self.assertIsNone(table.to_number(given))

	def test_identifiers_dates_and_phone_numbers_are_not_numbers(self):
		# These would poison sums/means if they were read as quantities.
		for given in ("SKU-1001", "ID-0042", "INV-2024-001", "15/01/2024", "2024-01-15", "2024-01-15 10:30:00", "+966 50 123 4567", "966-50-123", "12 Elm 3", "A1B2", "Room 12 / 2024"):
			with self.subTest(given):
				self.assertIsNone(table.to_number(given))

	def test_european_grouping_is_not_silently_misread(self):
		self.assertIsNone(table.to_number("1.234,50"))  # would otherwise become 1.2345


class TestTable(unittest.TestCase):
	def test_describe(self):
		d = table.describe(COLS, ROWS)
		self.assertEqual(d["rows"], 6)
		by = {c["name"]: c for c in d["columns"]}
		amount = by["Amount"]
		self.assertEqual((amount["type"], amount["non_empty"], amount["empty"]), ("number", 5, 1))
		self.assertEqual((amount["min"], amount["max"], amount["sum"], amount["mean"]), (-50.0, 1000.0, 1331.0, 266.2))
		region = by["Region"]
		self.assertEqual((region["type"], region["distinct"], region["sample"]), ("text", 3, ["North", "North", "South"]))
		self.assertEqual(len(d["head"]), 5)
		self.assertEqual(d["head"][0], {"Region": "North", "Product": "A", "Amount": "100", "Qty": "1"})

	def test_describe_treats_mostly_text_columns_as_text(self):
		rows = [[str(i)] for i in range(8)] + [["x"], ["y"]]
		self.assertEqual(table.describe(["c"], rows)["columns"][0]["type"], "text")  # 80% < 90%
		rows = [[str(i)] for i in range(9)] + [["x"]]
		self.assertEqual(table.describe(["c"], rows)["columns"][0]["type"], "number")

	def test_describe_keeps_identifier_and_date_columns_as_text(self):
		rows = [[f"SKU-{1000 + i}", f"{i + 1:02d}/03/2024"] for i in range(10)]
		cols = table.describe(["sku", "date"], rows)["columns"]
		self.assertEqual([c["type"] for c in cols], ["text", "text"])

	def test_aggregate_without_group(self):
		def agg(func, column="Amount", **kw):
			return table.aggregate(COLS, ROWS, column=column, func=func, **kw)

		self.assertEqual(agg("sum")["value"], 1331.0)
		self.assertEqual(agg("mean")["value"], 266.2)
		self.assertEqual(agg("min")["value"], -50.0)
		self.assertEqual(agg("max")["value"], 1000.0)
		self.assertEqual(agg("median")["value"], 100.0)
		self.assertEqual(agg("count")["value"], 6)
		self.assertEqual(agg("count_distinct", "Region")["value"], 3)
		self.assertEqual(agg("sum")["rows_used"], 6)
		self.assertEqual(table.aggregate(COLS, ROWS, column=None, func="count")["value"], 6)
		self.assertEqual(agg("sum", column="amount")["value"], 1331.0)  # column names are case-insensitive
		self.assertIsNone(agg("sum", "Product")["value"])  # nothing numeric to add up

	def test_median_of_even_count(self):
		rows = [["1"], ["2"], ["3"], ["10"]]
		self.assertEqual(table.aggregate(["n"], rows, column="n", func="median")["value"], 2.5)

	def test_aggregate_group_by_orders_largest_first_and_puts_empty_last(self):
		rows = ROWS + [["West", "D", "", "7"]]
		out = table.aggregate(COLS, rows, column="Amount", func="sum", group_by="Region")
		self.assertEqual([(r["Region"], r["sum"]) for r in out["results"]], [("South", 950.0), ("North", 350.5), ("East", 30.5), ("West", None)])
		self.assertEqual((out["groups"], out["truncated"], out["rows_used"]), (4, False, 7))
		counts = table.aggregate(COLS, ROWS, column=None, func="count", group_by="Region")
		self.assertEqual({r["Region"]: r["count"] for r in counts["results"]}, {"North": 2, "South": 2, "East": 2})

	def test_group_by_with_every_function(self):
		expected = {
			"sum": {"North": 350.5, "South": 950.0, "East": 30.5},
			"mean": {"North": 175.25, "South": 475.0, "East": 30.5},
			"min": {"North": 100.0, "South": -50.0, "East": 30.5},
			"max": {"North": 250.5, "South": 1000.0, "East": 30.5},
			"median": {"North": 175.25, "South": 475.0, "East": 30.5},
		}
		for func, per_region in expected.items():
			with self.subTest(func):
				out = table.aggregate(COLS, ROWS, column="Amount", func=func, group_by="Region")
				self.assertEqual({r["Region"]: r[func] for r in out["results"]}, per_region)
		distinct = table.aggregate(COLS, ROWS, column="Product", func="count_distinct", group_by="Region")
		self.assertEqual({r["Region"]: r["count_distinct"] for r in distinct["results"]}, {"North": 2, "South": 2, "East": 2})

	def test_group_limit_is_clamped(self):
		rows = [[f"g{i}", "1"] for i in range(120)]
		out = table.aggregate(["g", "n"], rows, column="n", func="sum", group_by="g", limit=1000)
		self.assertEqual(len(out["results"]), table.MAX_RESULT_ROWS)
		self.assertTrue(out["truncated"])
		self.assertEqual(out["groups"], 120)
		self.assertEqual(len(table.aggregate(["g", "n"], rows, column="n", func="sum", group_by="g", limit=3)["results"]), 3)
		self.assertEqual(len(table.aggregate(["g", "n"], rows, column="n", func="sum", group_by="g", limit=0)["results"]), 20)

	def test_every_filter_operator(self):
		def n(*filters):
			return table.select_rows(COLS, ROWS, filters=list(filters))["matched"]

		self.assertEqual(n({"column": "Amount", "op": "gt", "value": 100}), 2)  # 250.5, 1000
		self.assertEqual(n({"column": "Amount", "op": "gte", "value": "100"}), 3)
		self.assertEqual(n({"column": "Amount", "op": "lt", "value": 100}), 2)  # -50, 30.5 (the empty cell never matches)
		self.assertEqual(n({"column": "Amount", "op": "lte", "value": 100}), 3)
		self.assertEqual(n({"column": "Region", "op": "eq", "value": "north"}), 2)  # case-insensitive text
		self.assertEqual(n({"column": "Qty", "op": "eq", "value": 3}), 1)  # numeric equality
		self.assertEqual(n({"column": "Amount", "op": "eq", "value": "100.0"}), 1)
		self.assertEqual(n({"column": "Region", "op": "ne", "value": "North"}), 4)
		self.assertEqual(n({"column": "Product", "op": "contains", "value": "a"}), 3)
		self.assertEqual(n({"column": "region", "value": "South"}), 2)  # op defaults to eq; column case-insensitive
		self.assertEqual(n({"column": "Region", "op": "eq", "value": "North"}, {"column": "Amount", "op": "gt", "value": 150}), 1)  # AND
		self.assertEqual(n({"column": "Amount", "op": "gt", "value": "not a number"}), 0)
		self.assertEqual(table.apply_filters(COLS, ROWS, None), ROWS)

	def test_filtered_aggregate(self):
		out = table.aggregate(COLS, ROWS, column="Amount", func="sum", filters=[{"column": "Region", "op": "eq", "value": "South"}])
		self.assertEqual((out["value"], out["rows_used"]), (950.0, 2))

	def test_select_rows_limit(self):
		out = table.select_rows(COLS, ROWS, limit=2)
		self.assertEqual((out["matched"], len(out["rows"]), out["truncated"]), (6, 2, True))
		self.assertEqual(out["rows"][1]["Product"], "B")

	def test_errors(self):
		with self.assertRaisesRegex(table.TableError, "Unknown column 'Nope'.*Region, Product, Amount, Qty"):
			table.aggregate(COLS, ROWS, column="Nope", func="sum")
		with self.assertRaisesRegex(table.TableError, "Unknown column"):
			table.aggregate(COLS, ROWS, column="Amount", func="sum", group_by="Nope")
		with self.assertRaisesRegex(table.TableError, "Unknown function 'avg'"):
			table.aggregate(COLS, ROWS, column="Amount", func="avg")
		with self.assertRaisesRegex(table.TableError, "needs a column"):
			table.aggregate(COLS, ROWS, column=None, func="sum")
		with self.assertRaisesRegex(table.TableError, "Unknown filter op"):
			table.select_rows(COLS, ROWS, filters=[{"column": "Region", "op": "regex", "value": "."}])
		with self.assertRaisesRegex(table.TableError, "Unknown column ''"):
			table.select_rows(COLS, ROWS, filters=[{"value": 1}])

	def test_a_single_filter_object_is_accepted_without_the_list(self):
		self.assertEqual(table.select_rows(COLS, ROWS, filters={"column": "Region", "value": "North"})["matched"], 2)

	def test_malformed_filters_raise_table_error_not_attribute_error(self):
		for bad in ("Region=North", ["Region", "eq", "North"], 5, None):
			with self.subTest(repr(bad)):
				with self.assertRaises(table.TableError):
					table.select_rows(COLS, ROWS, filters=[bad])


# ---------------------------------------------------------------------------
# calc.py
# ---------------------------------------------------------------------------


class TestCalc(unittest.TestCase):
	def val(self, expr):
		return calc.calculate(expr)["value"]

	def test_precedence_and_operators(self):
		self.assertEqual(self.val("2 + 3 * 4"), 14)
		self.assertEqual(self.val("(2 + 3) * 4"), 20)
		self.assertEqual(self.val("10 / 4"), 2.5)
		self.assertEqual(self.val("7 // 2"), 3)
		self.assertEqual(self.val("7 % 3"), 1)
		self.assertEqual(self.val("-2 ** 2"), -4)  # same as the maths convention
		self.assertEqual(self.val("2 ^ 3 ^ 2"), 512)  # ^ is power, right-associative
		self.assertEqual(self.val("2 ** -1"), 0.5)
		self.assertEqual(self.val("+5 - -3"), 8)
		self.assertEqual(self.val("0.1 + 0.2"), 0.3)  # float noise is rounded away

	def test_thousands_separators_and_functions_with_several_arguments(self):
		self.assertEqual(self.val("1,234.5 * 2"), 2469.0)
		self.assertEqual(self.val("1,000,000 / 4"), 250000.0)
		self.assertEqual(self.val("max(3,9)"), 9)
		self.assertEqual(self.val("max(3, 9, 4)"), 9)
		self.assertEqual(self.val("min(5, 2) + 1"), 3)
		self.assertEqual(self.val("sum(1, 2, 3)"), 6)
		self.assertEqual(self.val("round(2.567, 2)"), 2.57)
		self.assertEqual(self.val("round(2.567,2)"), 2.57)
		self.assertEqual(self.val("round(1234.5678, 1) * 2"), 2469.2)

	def test_functions_and_constants(self):
		self.assertEqual(self.val("sqrt(16)"), 4.0)
		self.assertEqual(self.val("abs(-3)"), 3)
		self.assertEqual(self.val("floor(2.7) + ceil(2.1)"), 5)
		self.assertEqual(self.val("log10(1000)"), 3.0)
		self.assertEqual(self.val("exp(0)"), 1.0)
		self.assertAlmostEqual(self.val("pi * 2"), 2 * math.pi, places=9)
		self.assertAlmostEqual(self.val("e"), math.e, places=9)
		self.assertAlmostEqual(self.val("sin(0) + cos(0) + tan(0)"), 1.0)
		self.assertAlmostEqual(self.val("log(e)"), 1.0)

	def test_result_echoes_the_original_expression(self):
		self.assertEqual(calc.calculate(" 1+1 ")["expression"], " 1+1 ")

	def test_code_execution_is_impossible(self):
		for expr in (
			"__import__('os').system('id')",
			"__import__('os')",
			"().__class__.__bases__",
			"(1).__add__(2)",
			"'a'.upper()",
			"open('/etc/passwd')",
			"eval('1+1')",
			"exec('x=1')",
			"print(1)",
			"len([1])",
			"os",
			"x",
			"True",
			"None",
			"'text'",
			"[1, 2][0]",
			"{1: 2}",
			"lambda: 1",
			"[i for i in range(3)]",
			"1 if 1 else 2",
			"(x := 5)",
			"max(1, 2, key=abs)",
			"round(2.5, ndigits=0)",
			"sum([1, 2])",
			"abs",
			"1 < 2",
			"not 1",
			"1 and 2",
			"~5",
			"5 << 2",
			"5 | 2",
			"5 & 2",
			"f'{1}'",
			"a.b",
		):
			with self.subTest(expr):
				with self.assertRaises(calc.CalcError):
					calc.calculate(expr)

	def test_other_functions_cannot_be_reached_through_name_tricks(self):
		for expr in ("math.sqrt(4)", "abs.__call__(-1)", "getattr(1, 'real')", "ABS(-1)", "Sqrt(4)"):
			with self.subTest(expr):
				with self.assertRaises(calc.CalcError):
					calc.calculate(expr)

	def test_exponent_limits(self):
		with self.assertRaisesRegex(calc.CalcError, "Exponent too large"):
			calc.calculate("2 ** 10000")
		with self.assertRaisesRegex(calc.CalcError, "Exponent too large"):
			calc.calculate("9 ** 9 ** 9")
		self.assertEqual(self.val("2 ** 1000"), 2**1000)  # still fine at the limit
		self.assertEqual(self.val("10 ** -400"), 0.0)

	def test_stacked_powers_cannot_exhaust_memory(self):
		# every single exponent is within the limit, but the magnitudes compound
		start = time.monotonic()
		for expr in ("((10**1000)**1000)**1000", "((9**999)**999)**999", "(10**1000)**1000"):
			with self.subTest(expr):
				with self.assertRaisesRegex(calc.CalcError, "too large"):
					calc.calculate(expr)
		self.assertLess(time.monotonic() - start, 2.0, "rejection must be immediate, not after computing a huge number")

	def test_results_that_cannot_be_serialised_are_refused(self):
		# > 4300 digits makes json.dumps raise; the tool result must never reach that point
		with self.assertRaisesRegex(calc.CalcError, "too large"):
			calc.calculate("(10**999)*(10**999)*(10**999)*(10**999)*(10**999)")
		out = calc.calculate("10**999 * 10**999")
		json.dumps(out)  # large but representable results are still returned

	def test_arithmetic_failures_are_calc_errors(self):
		for expr, msg in (
			("1/0", "Division by zero"),
			("1//0", "Division by zero"),
			("5 % 0", "Division by zero"),
			("0 ** -1", "Division by zero"),
			("sqrt(-1)", "Could not evaluate"),
			("log(0)", "Could not evaluate"),
			("1 +", "Could not evaluate"),
			("((1)", "Could not evaluate"),
			("abs()", "Could not evaluate"),
			("sqrt(1, 2)", "Could not evaluate"),
			("٣ + ٤", "Could not evaluate"),  # Arabic-Indic digits are not numeric literals in Python
			("1e999", "not a finite"),
			("10.0 ** 999", "Could not evaluate"),
			("1e308 * 10", "not a finite"),
			("exp(1000)", "Could not evaluate"),
		):
			with self.subTest(expr):
				with self.assertRaisesRegex(calc.CalcError, msg):
					calc.calculate(expr)

	def test_input_size_and_emptiness(self):
		for expr in ("", "   ", None):
			with self.assertRaises(calc.CalcError):
				calc.calculate(expr)
		self.assertEqual(self.val("1" + "+1" * 248), 249)  # 497 chars: fine
		with self.assertRaisesRegex(calc.CalcError, "500"):
			calc.calculate("1" + "+1" * 300)

	def test_pathologically_deep_nesting_is_a_calc_error(self):
		limit = sys.getrecursionlimit()
		try:
			sys.setrecursionlimit(len(inspect.stack()) + 40)  # leave the evaluator only a few dozen frames
			with self.assertRaises(calc.CalcError):
				calc.calculate("-" * 480 + "1")
		finally:
			sys.setrecursionlimit(limit)


# ---------------------------------------------------------------------------
# knowledge/rank.py
# ---------------------------------------------------------------------------


class TestRank(unittest.TestCase):
	DOCS = [
		"The quarterly invoice was sent to the customer on Monday.",
		"Our warehouse stores spare parts for delivery vans.",
		"Payment terms are thirty days after the invoice date.",
		"Employees receive annual leave of twenty one days.",
	]

	def test_tokenize(self):
		self.assertEqual(rank.tokenize("Hello, World! a b 5 x9"), ["hello", "world", "5", "x9"])
		self.assertEqual(rank.tokenize("فاتورة رقم ١٢٣"), ["فاتورة", "رقم", "١٢٣"])
		self.assertEqual(rank.tokenize(None), [])
		self.assertEqual(rank.tokenize(""), [])

	def test_bm25_ranks_the_right_chunk_first(self):
		scores = rank.keyword_scores("warehouse delivery vans", self.DOCS)
		self.assertEqual(scores.index(max(scores)), 1)
		self.assertEqual(max(scores), 1.0)
		self.assertEqual(scores[3], 0.0)
		self.assertTrue(all(0.0 <= s <= 1.0 for s in scores))

	def test_rare_terms_outweigh_common_ones(self):
		docs = ["invoice invoice invoice invoice", "invoice zebra"]
		scores = rank.keyword_scores("invoice zebra", docs)
		self.assertGreater(scores[1], scores[0])

	def test_shorter_document_wins_on_equal_term_frequency(self):
		docs = ["budget " + "filler " * 80, "budget plan"]
		scores = rank.keyword_scores("budget", docs)
		self.assertGreater(scores[1], scores[0])

	def test_arabic_keywords(self):
		docs = ["فاتورة المبيعات للعميل الشهرية", "جدول الإجازات السنوية للموظفين", "سياسة المشتريات"]
		scores = rank.keyword_scores("الإجازات السنوية", docs)
		self.assertEqual(scores.index(max(scores)), 1)
		self.assertEqual(scores[0], 0.0)

	def test_keyword_edge_cases(self):
		self.assertEqual(rank.keyword_scores("anything", []), [])
		self.assertEqual(rank.keyword_scores("", ["a doc"]), [0.0])
		self.assertEqual(rank.keyword_scores("a b", ["a b doc"]), [0.0])  # single letters are not terms
		self.assertEqual(rank.keyword_scores("zzz", ["", ""]), [0.0, 0.0])
		self.assertEqual(rank.keyword_scores("zzz", self.DOCS), [0.0] * 4)

	def test_cosine(self):
		self.assertAlmostEqual(rank.cosine([1, 2, 3], [1, 2, 3]), 1.0)
		self.assertAlmostEqual(rank.cosine([1, 0], [0, 1]), 0.0)
		self.assertAlmostEqual(rank.cosine([1, 0], [-1, 0]), -1.0)
		self.assertAlmostEqual(rank.cosine([1, 2], [10, 20]), 1.0)  # scale-invariant
		self.assertEqual(rank.cosine([0, 0], [1, 1]), 0.0)  # zero vector
		self.assertEqual(rank.cosine([1, 2], [1, 2, 3]), 0.0)  # mismatched dimensions
		self.assertEqual(rank.cosine([], [1]), 0.0)
		self.assertEqual(rank.cosine(None, [1]), 0.0)

	def test_hybrid_without_embeddings_is_keyword_search(self):
		ranked = rank.hybrid_rank("invoice", self.DOCS)
		self.assertEqual(sorted(i for i, _ in ranked), [0, 2])  # only chunks that mention it
		self.assertGreaterEqual(ranked[0][1], ranked[1][1])
		self.assertEqual(ranked, rank.hybrid_rank("invoice", self.DOCS, query_embedding=[1.0], doc_embeddings=None))
		self.assertEqual(ranked, rank.hybrid_rank("invoice", self.DOCS, query_embedding=None, doc_embeddings=[[1.0]] * 4))

	def test_hybrid_semantic_match_without_shared_words(self):
		docs = ["puppy training guide", "invoice payment terms", "rain forecast for tomorrow"]
		embeddings = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
		self.assertEqual(rank.hybrid_rank("canine", docs), [])  # keywords alone find nothing
		ranked = rank.hybrid_rank("canine", docs, query_embedding=[1.0, 0, 0], doc_embeddings=embeddings)
		self.assertEqual([i for i, _ in ranked], [0])
		self.assertAlmostEqual(ranked[0][1], 0.6)

	def test_hybrid_blend_and_partial_embeddings(self):
		docs = ["invoice payment", "invoice only here", "nothing relevant"]
		ranked = dict(rank.hybrid_rank("invoice", docs, query_embedding=[1.0, 0], doc_embeddings=[[1.0, 0], None, [0, 1.0]], min_score=0))
		kw = rank.keyword_scores("invoice", docs)
		self.assertAlmostEqual(ranked[0], 0.6 * 1.0 + 0.4 * kw[0])  # blended
		self.assertAlmostEqual(ranked[1], kw[1])  # no embedding: keyword only
		self.assertAlmostEqual(ranked[2], 0.0)  # orthogonal and no keyword hit

	def test_hybrid_negative_similarity_never_subtracts(self):
		ranked = dict(rank.hybrid_rank("invoice", ["invoice"], query_embedding=[1.0, 0], doc_embeddings=[[-1.0, 0]], min_score=0))
		self.assertAlmostEqual(ranked[0], 0.4 * 1.0)

	def test_hybrid_min_score_and_ordering(self):
		docs = ["alpha beta", "alpha", "gamma"]
		everything = rank.hybrid_rank("alpha beta", docs, min_score=0)
		self.assertEqual(len(everything), 3)
		self.assertEqual([i for i, _ in everything], [0, 1, 2])
		self.assertEqual([i for i, _ in rank.hybrid_rank("alpha beta", docs, min_score=0.9)], [0])
		self.assertEqual(rank.hybrid_rank("alpha", []), [])


# ---------------------------------------------------------------------------
# routing.py
# ---------------------------------------------------------------------------


class TestRouting(unittest.TestCase):
	SETTINGS = {
		"default_model": "gpt-balanced",
		"model_fast": "gpt-fast",
		"model_reasoning": "gpt-think",
		"model_vision": "gpt-eyes",
		"model_coding": "gpt-code",
		"fallback_model": "gpt-fallback",
	}

	def test_allowed_models_ordered_and_deduplicated(self):
		self.assertEqual(
			routing.allowed_models(self.SETTINGS),
			["gpt-balanced", "gpt-fast", "gpt-think", "gpt-eyes", "gpt-code", "gpt-fallback"],
		)
		same = {"default_model": "m", "model_fast": "m", "model_coding": " m ", "fallback_model": "other"}
		self.assertEqual(routing.allowed_models(same), ["m", "other"])
		self.assertEqual(routing.allowed_models({"default_model": " x ", "model_fast": "", "model_vision": None}), ["x"])
		self.assertEqual(routing.allowed_models({}), [])

	def test_classify_slots(self):
		long_plain = "Please summarise what happened in the warehouse over the last week for the team. " * 2
		self.assertGreater(len(long_plain), 100)
		cases = [
			("describe this picture", True, False, "vision"),
			("```python\nprint(1)\n```", False, False, "coding"),
			("fix this traceback for me", False, False, "coding"),
			("write a SQL query for customers", False, False, "coding"),
			("explain why the margin dropped", False, False, "reasoning"),
			("compare these two suppliers", False, False, "reasoning"),
			("x " * 800, False, False, "reasoning"),  # very long
			("hi", False, False, "fast"),
			("what time is it", False, False, "fast"),
			(long_plain, False, False, "balanced"),
			(long_plain, False, True, "fast"),  # planner said the task is simple
		]
		for text, images, simple, expected in cases:
			with self.subTest(text[:30], images=images):
				self.assertEqual(routing.classify(text, has_images=images, simple=simple), expected)

	def test_classify_precedence(self):
		self.assertEqual(routing.classify("explain this python bug", has_images=False), "coding")  # code beats reasoning
		self.assertEqual(routing.classify("fix this python bug", has_images=True), "vision")  # images beat everything
		self.assertEqual(routing.classify("", has_images=False), "fast")
		self.assertEqual(routing.classify(None, has_images=False), "fast")

	def test_pick_model_routing_off(self):
		self.assertEqual(routing.pick_model(self.SETTINGS, "```code```", has_images=False), (None, "balanced"))
		self.assertEqual(routing.pick_model({**self.SETTINGS, "enable_model_routing": 0}, "hi", has_images=True), (None, "balanced"))

	def test_pick_model_routing_on(self):
		s = {**self.SETTINGS, "enable_model_routing": 1}
		self.assertEqual(routing.pick_model(s, "hi", has_images=False), ("gpt-fast", "fast"))
		self.assertEqual(routing.pick_model(s, "explain why", has_images=False), ("gpt-think", "reasoning"))
		self.assertEqual(routing.pick_model(s, "look", has_images=True), ("gpt-eyes", "vision"))
		self.assertEqual(routing.pick_model(s, "def f(): pass", has_images=False), ("gpt-code", "coding"))
		plain = "Please summarise what happened in the warehouse over the last week for the team. " * 2
		self.assertEqual(routing.pick_model(s, plain, has_images=False), (None, "balanced"))  # default model, no override

	def test_pick_model_unconfigured_or_blank_slot_uses_default(self):
		s = {"enable_model_routing": 1, "default_model": "d", "model_fast": "   "}
		self.assertEqual(routing.pick_model(s, "hi", has_images=False), (None, "fast"))
		self.assertEqual(routing.pick_model(s, "look", has_images=True), (None, "vision"))
		self.assertEqual(routing.pick_model({"enable_model_routing": 1}, "hi", has_images=False), (None, "fast"))
		padded = {"enable_model_routing": 1, "model_fast": "  gpt-fast  "}
		self.assertEqual(routing.pick_model(padded, "hi", has_images=False), ("gpt-fast", "fast"))


# ---------------------------------------------------------------------------
# web_search.py: Brave search, URL safety, fetch
# ---------------------------------------------------------------------------


class TestBraveSearch(unittest.TestCase):
	def server(self, body=None, **route):
		srv = PageServer({"/res/v1/web/search": Route(body if body is not None else brave_payload(), ctype="application/json", **route)})
		self.addCleanup(srv.stop)
		return srv

	def brave(self, srv, key="test-key", **kw):
		return ws.BraveSearch(key, endpoint=srv.url + "/res/v1/web/search", **kw)

	def test_parses_results_and_sends_key_and_query(self):
		srv = self.server(
			brave_payload(
				("<strong>ZatGo</strong> ERP", "https://www.zatgo.example/products", "Cloud <b>ERP</b> for Saudi   businesses"),
				("Docs", "http://docs.example.org/a?b=1", "Documentation"),
			)
		)
		results = self.brave(srv).search("zatgo erp", count=4)
		self.assertEqual([r.title for r in results], ["ZatGo ERP", "Docs"])
		self.assertEqual(results[0].url, "https://www.zatgo.example/products")
		self.assertEqual(results[0].domain, "zatgo.example")  # www. dropped
		self.assertEqual(results[0].snippet, "Cloud ERP for Saudi businesses")  # tags stripped, spaces collapsed
		self.assertEqual(results[1].domain, "docs.example.org")
		self.assertEqual(results[0].as_dict()["domain"], "zatgo.example")
		req = srv.requests[0]
		self.assertEqual(req["headers"]["X-Subscription-Token"], "test-key")
		self.assertEqual(req["headers"]["Accept"], "application/json")
		query = urllib.parse.parse_qs(urllib.parse.urlparse(req["path"]).query)
		self.assertEqual(query, {"q": ["zatgo erp"], "count": ["4"]})

	def test_count_and_query_are_bounded(self):
		srv = self.server()
		b = self.brave(srv)
		b.search("x" * 1000, count=99)
		b.search("q", count=0)
		b.search("q", count=-3)
		q = [urllib.parse.parse_qs(urllib.parse.urlparse(r["path"]).query) for r in srv.requests]
		self.assertEqual(len(q[0]["q"][0]), 400)
		self.assertEqual([x["count"] for x in q], [["10"], ["5"], ["1"]])  # 0 falls back to 5

	def test_unusable_result_urls_are_dropped(self):
		srv = self.server(
			brave_payload(
				("js", "javascript:alert(1)", "x"),
				("ftp", "ftp://files.example/a", "x"),
				("rel", "/relative/path", "x"),
				("none", "", "x"),
				("ok", "https://ok.example/", "fine"),
			)
		)
		self.assertEqual([r.url for r in self.brave(srv).search("q")], ["https://ok.example/"])

	def test_empty_and_odd_payloads(self):
		for body in (b"{}", b'{"web": {}}', b'{"web": {"results": []}}', b'{"web": null}'):
			with self.subTest(body):
				self.assertEqual(self.brave(self.server(body)).search("q"), [])

	def test_age_falls_back_to_page_age(self):
		body = b'{"web": {"results": [{"title": "t", "url": "https://a.example/", "description": "d", "page_age": "2026-01-02T00:00:00"}]}}'
		self.assertEqual(self.brave(self.server(body)).search("q")[0].age, "2026-01-02T00:00:00")

	def test_missing_key(self):
		srv = self.server()
		for key in ("", None):
			with self.assertRaisesRegex(ws.WebToolError, "no API key"):
				self.brave(srv, key=key).search("q")
		self.assertEqual(srv.requests, [])  # nothing was sent

	def test_http_errors_become_provider_errors_with_safe_messages(self):
		for status, code, retryable in ((401, "auth", False), (403, "auth", False), (429, "rate_limited", True), (500, "provider_unavailable", True), (422, "bad_request", False)):
			with self.subTest(status):
				srv = self.server(b'{"error": "secret internal detail"}', status=status)
				with self.assertRaises(ProviderError) as c:
					self.brave(srv).search("q")
				self.assertEqual((c.exception.code, c.exception.retryable), (code, retryable))
				self.assertNotIn("secret internal detail", c.exception.message)

	def test_non_json_and_unreachable_and_slow(self):
		with self.assertRaises(ProviderError) as c:
			self.brave(self.server(b"<html>gateway</html>")).search("q")
		self.assertEqual(c.exception.code, "network")
		dead = PageServer()
		dead.stop()
		with self.assertRaises(ProviderError) as c:
			ws.BraveSearch("k", endpoint=dead.url + "/x").search("q")
		self.assertTrue(c.exception.retryable)
		slow = self.server(delay=2.5)
		with self.assertRaises(ProviderError) as c:
			self.brave(slow, timeout=1).search("q")
		self.assertEqual(c.exception.code, "timeout")

	def test_get_provider(self):
		with self.assertRaisesRegex(ws.WebToolError, "turned off"):
			ws.get_provider({"enable_web_search": 0, "web_search_api_key": "k"})
		with self.assertRaisesRegex(ws.WebToolError, "Unknown web search provider 'Bing'"):
			ws.get_provider({"enable_web_search": 1, "web_search_provider": "Bing"})
		p = ws.get_provider({"local_only": 0, "enable_web_search": 1, "web_search_provider": "Brave", "web_search_api_key": "k"})
		self.assertIsInstance(p, ws.BraveSearch)
		self.assertEqual(p.api_key, "k")
		# the self-hosted provider is the default: it needs a URL, never a key
		p = ws.get_provider({"enable_web_search": 1, "web_search_url": "http://searxng:8080/"})
		self.assertIsInstance(p, ws.SearXNGSearch)
		self.assertEqual(p.base_url, "http://searxng:8080")
		self.assertFalse(hasattr(p, "api_key"))


class TestAssertPublicUrl(unittest.TestCase):
	def reject(self, url, pattern=None):
		with self.assertRaises(ws.WebToolError, msg=url) as c:
			ws.assert_public_url(url)
		if pattern:
			self.assertRegex(str(c.exception), pattern)

	def test_loopback_private_and_metadata_addresses(self):
		for url in (
			"http://127.0.0.1/",
			"http://127.0.0.1:8080/admin",
			"http://localhost/",
			"http://LOCALHOST:8080/",
			"http://localhost./",
			"http://10.0.0.5/",
			"http://10.255.255.255/",
			"http://172.16.0.1/",
			"http://172.31.255.254/",
			"http://192.168.1.1/",
			"http://169.254.169.254/latest/meta-data/",
			"http://[::1]/",
			"http://[::1]:8080/",
			"http://[fe80::1]/",
			"http://[fc00::1]/",
			"http://0.0.0.0/",
			"http://[::]/",
			"http://127.1/",  # shorthand for 127.0.0.1
			"http://2130706433/",  # 127.0.0.1 as one integer
			"http://0x7f.0.0.1/",
			"http://[::ffff:127.0.0.1]/",  # IPv4-mapped IPv6
			"http://[::ffff:10.0.0.1]/",
			"http://224.0.0.1/",  # multicast
			"http://240.0.0.1/",  # reserved
		):
			with self.subTest(url):
				self.reject(url, "not publicly reachable")

	def test_carrier_grade_nat_and_other_non_global_ranges(self):
		# 100.64.0.0/10 is neither "private" nor public: it is internal address space on cloud
		# providers (Alibaba's metadata service lives at 100.100.100.200) and Tailscale networks.
		for url in ("http://100.64.0.1/", "http://100.100.100.200/latest/meta-data/", "http://100.127.255.254/", "http://198.18.0.1/", "http://192.0.2.1/", "http://198.51.100.7/", "http://203.0.113.9/"):
			with self.subTest(url):
				self.reject(url, "not publicly reachable")

	def test_unsupported_schemes_and_shapes(self):
		for url in ("file:///etc/passwd", "ftp://example.com/", "gopher://example.com/", "javascript:alert(1)", "data:text/html,hi", "//example.com/", "example.com", "http:///path", "", "http://"):
			with self.subTest(repr(url)):
				self.reject(url, "Only http")

	def test_credentials_in_the_url(self):
		for url in ("http://user:pass@1.1.1.1/", "http://user@1.1.1.1/", "https://:pw@1.1.1.1/", "http://127.0.0.1\\@evil.example/"):
			with self.subTest(url):
				self.reject(url)
		self.reject("http://user:pass@1.1.1.1/", "credentials")

	def test_ports(self):
		for port in (22, 25, 3306, 5432, 6379, 8000, 9200, 11211, 65535):
			with self.subTest(port):
				self.reject(f"http://1.1.1.1:{port}/", "port")
		for url in ("http://1.1.1.1:80/", "https://1.1.1.1:443/", "http://1.1.1.1:8080/", "https://1.1.1.1:8443/", "http://1.1.1.1/", "https://1.1.1.1/"):
			with self.subTest(url):
				self.assertEqual(ws.assert_public_url(url), ["1.1.1.1"])

	def test_malformed_ports_are_a_clean_rejection(self):
		for url in ("http://1.1.1.1:99999/", "http://1.1.1.1:abc/", "http://1.1.1.1:-1/", "http://1.1.1.1:0/"):
			with self.subTest(url):
				self.reject(url)

	def test_unresolvable_host(self):
		self.reject("http://nonexistent-host.invalid/", "could not be resolved")

	def test_public_addresses_are_returned_for_pinning(self):
		self.assertEqual(ws.assert_public_url("http://8.8.8.8/"), ["8.8.8.8"])
		self.assertEqual(ws.assert_public_url("https://[2606:4700:4700::1111]/"), ["2606:4700:4700::1111"])

	def test_hostname_resolving_to_a_mix_is_rejected_if_any_address_is_internal(self):
		def fake_getaddrinfo(host, port, **kw):
			return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", port))]

		with mock.patch.object(ws.socket, "getaddrinfo", fake_getaddrinfo):
			self.reject("http://rebind.example/", "not publicly reachable")

		def all_public(host, port, **kw):
			return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

		with mock.patch.object(ws.socket, "getaddrinfo", all_public):
			self.assertEqual(ws.assert_public_url("http://fine.example/"), ["93.184.216.34"])


_REAL_ASSERT = ws.assert_public_url
_REAL_GETADDRINFO = socket.getaddrinfo
_REAL_CREATE_CONNECTION = socket.create_connection
STAND_IN_PUBLIC_IP = "93.184.216.34"  # a genuinely public address that the tests route to loopback


class FakeInternet:
	"""Plays DNS and routing for the fetch tests so the real `assert_public_url` and the real
	pinned connection code run unmodified:

	* `*.test` hostnames resolve to a public stand-in address, which connects to the local server;
	* `*.internal.test` hostnames resolve to 10.0.0.5 (a name that points at the internal network);
	* the server's random port is checked as if it were 8080, the only other thing a local server
	  cannot satisfy.
	"""

	def __init__(self, test: unittest.TestCase):
		self.checked: list[str] = []
		for patcher in (
			mock.patch.object(ws, "assert_public_url", side_effect=self._assert),
			mock.patch.object(ws.socket, "getaddrinfo", side_effect=self._getaddrinfo),
			mock.patch.object(ws.socket, "create_connection", side_effect=self._connect),
		):
			patcher.start()
			test.addCleanup(patcher.stop)

	def _assert(self, url):
		self.checked.append(url)
		parts = urllib.parse.urlparse(url)
		try:
			port = parts.port
		except ValueError:
			port = None
		if port and port >= 20000:
			url = urllib.parse.urlunparse(parts._replace(netloc=parts.netloc.rsplit(":", 1)[0] + ":8080"))
		return _REAL_ASSERT(url)

	@staticmethod
	def _getaddrinfo(host, port, *a, **kw):
		if host.endswith(".internal.test"):
			return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]
		if host.endswith(".test"):
			return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (STAND_IN_PUBLIC_IP, port))]
		return _REAL_GETADDRINFO(host, port, *a, **kw)

	@staticmethod
	def _connect(address, *a, **kw):
		host, port = address
		return _REAL_CREATE_CONNECTION(("127.0.0.1" if host == STAND_IN_PUBLIC_IP else host, port), *a, **kw)


class TestFetchUrl(unittest.TestCase):
	def setUp(self):
		self.net = FakeInternet(self)

	def server(self, routes=None):
		srv = PageServer(routes or {})
		self.addCleanup(srv.stop)
		return srv

	def url(self, srv, path="/", host="site.test"):
		return f"http://{srv.hostport(host)}{path}"

	def test_html_becomes_text_without_script_style_or_chrome(self):
		page = """<!doctype html><html><head><title> Pricing &amp; Plans </title>
		<style>body{color:red}</style><script>var secret = 'do not show';</script></head>
		<body><nav>Home | About</nav><h1>Plans</h1><p>Starter costs <b>99</b> SAR.</p>
		<script>alert('x')</script><noscript>enable js</noscript><div>Second block</div>
		<ul><li>one</li><li>two</li></ul><form><input value="v">Login form</form>
		<svg><text>icon</text></svg><footer>Copyright</footer></body></html>"""
		srv = self.server({"/p": Route(page)})
		out = ws.fetch_url(self.url(srv, "/p"))
		self.assertEqual(out["title"], "Pricing & Plans")
		self.assertEqual(out["domain"], "site.test")
		text = out["text"]
		for kept in ("Plans", "Starter costs", "99", "SAR.", "Second block", "one", "two"):
			self.assertIn(kept, text)
		for dropped in ("do not show", "alert", "color:red", "Home | About", "enable js", "Login form", "icon", "Copyright", "Pricing"):
			self.assertNotIn(dropped, text)
		self.assertFalse(out["truncated"])
		self.assertEqual(out["url"], self.url(srv, "/p"))

	def test_request_headers_and_pinned_connection(self):
		# The hostname resolves to nothing the server listens on: the only way to reach it is the
		# already-validated address, and the Host header must still carry the original name.
		srv = self.server({"/": Route("<p>hello</p>")})
		out = ws.fetch_url(self.url(srv, "/", host="pinned-host.test"))
		self.assertIn("hello", out["text"])
		req = srv.requests[0]
		self.assertEqual(req["headers"]["Host"], f"pinned-host.test:{srv.port}")
		self.assertEqual(req["headers"]["User-Agent"], "ZatGoChatAI/1.0")
		self.assertIn("text/html", req["headers"]["Accept"])

	def test_connection_goes_to_the_validated_address_not_a_second_lookup(self):
		# DNS rebinding: a resolver that answers differently the second time must not be consulted again.
		srv = self.server({"/": Route("<p>pinned</p>")})
		lookups = []
		first = FakeInternet._getaddrinfo

		def one_shot(host, port, *a, **kw):
			if host != "rebind.test":  # the socket layer resolves the already-validated literal address itself
				return first(host, port, *a, **kw)
			lookups.append(host)
			if len(lookups) > 1:
				return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]  # the "rebound" answer
			return first(host, port, *a, **kw)

		with mock.patch.object(ws.socket, "getaddrinfo", side_effect=one_shot):
			self.assertIn("pinned", ws.fetch_url(self.url(srv, "/", host="rebind.test"))["text"])
		self.assertEqual(lookups, ["rebind.test"], "the host name was resolved once, by the validation step")

	def test_plain_text_and_missing_content_type(self):
		srv = self.server({"/t": Route("line one\n\n\nline two <b>kept</b>", ctype="text/plain; charset=utf-8"), "/n": Route("no type", ctype=None)})
		out = ws.fetch_url(self.url(srv, "/t"))
		self.assertEqual(out["text"], "line one\n\n\nline two <b>kept</b>")  # not parsed as HTML
		self.assertEqual(out["title"], "")
		self.assertIn("no type", ws.fetch_url(self.url(srv, "/n"))["text"])

	def test_declared_charset_is_used_and_unknown_charsets_do_not_crash(self):
		arabic = "مرحبا بالعالم"
		srv = self.server(
			{
				"/cp": Route(f"<p>{arabic}</p>".encode("cp1256"), ctype="text/html; charset=windows-1256"),
				"/bogus": Route(f"<p>{arabic}</p>".encode(), ctype="text/html; charset=no-such-encoding"),
				"/bad": Route(b"<p>caf\xe9 \xff ok</p>", ctype="text/html; charset=utf-8"),
			}
		)
		self.assertIn(arabic, ws.fetch_url(self.url(srv, "/cp"))["text"])
		self.assertIn(arabic, ws.fetch_url(self.url(srv, "/bogus"))["text"])  # falls back to UTF-8
		self.assertIn("ok", ws.fetch_url(self.url(srv, "/bad"))["text"])  # invalid bytes are replaced, not fatal

	def test_unsupported_content_types(self):
		kinds = (("pdf", "application/pdf"), ("png", "image/png"), ("json", "application/json"), ("zip", "application/zip"), ("js", "text/javascript"))
		srv = self.server({f"/{n}": Route(b"x", ctype=c) for n, c in kinds})
		for name, _ in kinds:
			with self.subTest(name):
				with self.assertRaisesRegex(ws.WebToolError, "Unsupported content type"):
					ws.fetch_url(self.url(srv, "/" + name))

	def test_http_error_statuses(self):
		srv = self.server({"/404": Route("gone", status=404), "/500": Route("boom", status=500), "/loc": Route(b"", status=302, ctype=None)})
		for path, code in (("/404", 404), ("/500", 500), ("/loc", 302)):  # a redirect with no Location is just an error
			with self.subTest(path):
				with self.assertRaisesRegex(ws.WebToolError, f"HTTP {code}"):
					ws.fetch_url(self.url(srv, path))

	def test_response_size_and_text_caps(self):
		srv = self.server({"/big": Route("<html><body><p>" + "A" * 3_000_000 + "</p></body></html>")})
		out = ws.fetch_url(self.url(srv, "/big"))
		self.assertTrue(out["truncated"])
		self.assertEqual(len(out["text"]), ws.MAX_FETCH_CHARS)
		small = self.server({"/s": Route("<p>" + "B" * (ws.MAX_FETCH_CHARS + 500) + "</p>")})
		out = ws.fetch_url(self.url(small, "/s"))
		self.assertTrue(out["truncated"])  # long page, but under the byte cap
		self.assertLessEqual(len(out["text"]), ws.MAX_FETCH_CHARS)

	def test_redirects_are_followed_and_every_hop_validated(self):
		srv = self.server()
		srv.routes.update(
			{
				"/start": redirect("/middle"),  # relative
				"/middle": redirect(f"http://{srv.hostport('b.test')}/end", status=301),  # absolute, other host
				"/end": Route("<p>arrived</p>"),
			}
		)
		out = ws.fetch_url(self.url(srv, "/start", host="a.test"))
		self.assertIn("arrived", out["text"])
		self.assertEqual(out["url"], f"http://{srv.hostport('b.test')}/end")
		self.assertEqual(out["domain"], "b.test")
		self.assertEqual([urllib.parse.urlparse(u).path for u in self.net.checked], ["/start", "/middle", "/end"])
		self.assertEqual(srv.requests[2]["headers"]["Host"], srv.hostport("b.test"))

	def test_redirects_into_internal_space_are_refused_before_any_request(self):
		srv = self.server()
		port = srv.port
		for target in (
			f"http://127.0.0.1:{port}/secret",  # loopback by IP
			f"http://localhost:{port}/secret",
			f"//127.0.0.1:{port}/secret",  # scheme-relative
			"http://169.254.169.254/latest/meta-data/",  # cloud metadata
			"http://100.100.100.200/latest/meta-data/",  # Alibaba-style metadata (carrier-grade NAT range)
			"http://10.0.0.1/",
			"http://[::1]/",
			f"http://rebind.internal.test:{port}/secret",  # a public-looking name that resolves to 10.0.0.5
			"file:///etc/passwd",
			"ftp://example.com/x",
			"http://user:pw@a.test/x",
			"http://a.test:22/x",
		):
			with self.subTest(target):
				srv.requests.clear()
				srv.routes.clear()
				srv.routes["/start"] = redirect(target)
				srv.routes["/secret"] = Route("TOP SECRET")
				with self.assertRaises(ws.WebToolError):
					ws.fetch_url(self.url(srv, "/start", host="a.test"))
				self.assertEqual([r["path"] for r in srv.requests], ["/start"], "the internal target was never requested")

	def test_redirect_chain_limit(self):
		srv = self.server()
		srv.routes["/loop"] = redirect(f"http://{srv.hostport('a.test')}/loop")
		with self.assertRaisesRegex(ws.WebToolError, "Too many redirects"):
			ws.fetch_url(self.url(srv, "/loop"))
		self.assertEqual(len(srv.requests), ws.MAX_REDIRECTS + 1)
		# exactly MAX_REDIRECTS redirects followed by a page still works
		ok = self.server()
		for i in range(ws.MAX_REDIRECTS):
			ok.routes[f"/r{i}"] = redirect(f"/r{i + 1}")
		ok.routes[f"/r{ws.MAX_REDIRECTS}"] = Route("<p>made it</p>")
		self.assertIn("made it", ws.fetch_url(self.url(ok, "/r0"))["text"])

	def test_unreachable_page_is_a_clean_error(self):
		dead = PageServer()
		dead.stop()
		with self.assertRaisesRegex(ws.WebToolError, "could not be reached"):
			ws.fetch_url(self.url(dead, "/"))

	def test_slow_headers_time_out_cleanly(self):
		srv = self.server({"/slow": Route("<p>late</p>", delay=2.5)})
		with self.assertRaisesRegex(ws.WebToolError, "could not be reached"):
			ws.fetch_url(self.url(srv, "/slow"), timeout=1)

	def test_stalled_body_is_a_clean_error_not_a_raw_exception(self):
		# headers arrive, then the server goes silent: must surface as WebToolError
		srv = self.server({"/stall": Route("<p>" + "x" * 5000 + "</p>", stall=3)})
		start = time.monotonic()
		with self.assertRaises(ws.WebToolError):
			ws.fetch_url(self.url(srv, "/stall"), timeout=1)
		self.assertLess(time.monotonic() - start, 2.5)

	def test_dribbling_server_cannot_hold_the_worker_past_the_deadline(self):
		srv = self.server({"/drip": Route("<p>" + "x" * 400 + "</p>", dribble=(8, 0.25))})
		start = time.monotonic()
		with self.assertRaisesRegex(ws.WebToolError, "too long"):
			ws.fetch_url(self.url(srv, "/drip"), timeout=1)
		self.assertLess(time.monotonic() - start, 4.5)

	def test_body_shorter_than_declared_does_not_crash(self):
		srv = self.server({"/cut": Route("<p>complete sentence here</p>", truncate_to=12)})
		try:
			out = ws.fetch_url(self.url(srv, "/cut"))
		except ws.WebToolError:
			return  # a clean refusal is fine too
		self.assertIsInstance(out["text"], str)

	def test_loopback_server_is_refused_by_the_real_check(self):
		srv = self.server({"/": Route("internal")})
		for host in ("127.0.0.1", "localhost"):
			with self.assertRaises(ws.WebToolError):
				ws.fetch_url(f"http://{host}:{srv.port}/")
		self.assertEqual(srv.requests, [])


if __name__ == "__main__":
	unittest.main()



class TestContextBudget(unittest.TestCase):
	"""core/context.py: fitting history to a token budget and compacting context JSON."""

	def _msgs(self, n, size=200):
		return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i:03d} " + "x" * size} for i in range(n)]

	def test_estimates_are_conservative_for_arabic(self):
		from zatgo_core.chat_ai.core.context import estimate_tokens

		self.assertEqual(estimate_tokens(""), 0)
		self.assertGreater(estimate_tokens("مرحبا بكم في النظام" * 10), estimate_tokens("hello there in the system" * 10) * 1.5)

	def test_fit_keeps_the_newest_and_reports_what_it_dropped(self):
		from zatgo_core.chat_ai.core.context import estimate_tokens, fit_history

		msgs = self._msgs(40)
		one = estimate_tokens(msgs[0]["content"])
		kept, dropped = fit_history(msgs, one * 10 + 5)
		self.assertEqual([m["content"][:4] for m in kept], [f"m{i:03d}" for i in range(30, 40)])
		self.assertEqual([m["content"][:4] for m in dropped], [f"m{i:03d}" for i in range(30)])
		self.assertEqual(len(kept) + len(dropped), 40)  # nothing lost, nothing duplicated

	def test_message_count_cap_applies_too(self):
		from zatgo_core.chat_ai.core.context import fit_history

		kept, dropped = fit_history(self._msgs(20, size=5), 10**6, max_messages=6)
		self.assertEqual((len(kept), len(dropped)), (6, 14))
		kept, dropped = fit_history(self._msgs(5, size=5), 10**6, max_messages=0)  # 0 = no count cap
		self.assertEqual((len(kept), len(dropped)), (5, 0))

	def test_the_newest_messages_are_kept_even_over_budget_but_clipped(self):
		from zatgo_core.chat_ai.core.context import estimate_tokens, fit_history

		huge = [{"role": "user", "content": "first"}, {"role": "assistant", "content": "HEAD " + "y" * 200000 + " TAIL"}]
		kept, dropped = fit_history(huge, 500)
		self.assertEqual(len(kept), 2)
		clipped = kept[-1]["content"]
		self.assertLess(estimate_tokens(clipped), 600)
		self.assertTrue(clipped.startswith("HEAD") and clipped.endswith("TAIL"))
		self.assertIn("shortened", clipped)
		self.assertEqual(huge[1]["content"][:4], "HEAD")  # the input is not mutated

	def test_empty_and_degenerate_input(self):
		from zatgo_core.chat_ai.core.context import fit_history

		self.assertEqual(fit_history([], 100), ([], []))
		self.assertEqual(fit_history(None, 100), ([], []))
		kept, dropped = fit_history([{"role": "user", "content": "a"}], 0)
		self.assertEqual((len(kept), dropped), (1, []))

	def test_compact_json_is_always_valid_and_drops_low_priority_keys_first(self):
		import json

		from zatgo_core.chat_ai.core.context import compact_json

		ctx = {
			"current_user": {"user": "a@b.c"}, "entity_memory": {"customer": "ACME"},
			"recent_documents": ["doc" * 50] * 50, "workspace_context": {"name": "w" * 3000},
		}
		out = json.loads(compact_json(ctx, 600))  # parses: the old [:6000] cut mid-string
		self.assertNotIn("recent_documents", out)
		self.assertEqual(out["current_user"], {"user": "a@b.c"})
		self.assertEqual(out["entity_memory"], {"customer": "ACME"})
		small = {"a": 1}
		self.assertEqual(json.loads(compact_json(small, 600)), small)
		impossible = json.loads(compact_json({"current_user": {"x": "z" * 5000}}, 100))
		self.assertTrue(impossible.get("truncated") or len(json.dumps(impossible)) <= 100)
