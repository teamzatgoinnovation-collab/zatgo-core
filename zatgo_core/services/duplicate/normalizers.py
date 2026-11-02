"""Pure normalisers for duplicate matching -- no database, no Frappe.

Each returns the canonical comparison key of a raw value ("" when the value carries nothing to compare).
Stored values are never rewritten; only the keys are compared.
"""

from __future__ import annotations

import re
import unicodedata

_ARABIC_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_ARABIC_DIGITS.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})  # Persian / Urdu forms
_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # harakat, Quranic marks, tatweel
_LETTER_FOLD = {
    ord("أ"): "ا", ord("إ"): "ا", ord("آ"): "ا", ord("ٱ"): "ا",
    ord("ى"): "ي", ord("ئ"): "ي", ord("ة"): "ه", ord("ؤ"): "و", ord("ک"): "ك", ord("ی"): "ي",
}  # fmt: skip
_SPACES = re.compile(r"\s+")
_PHONE_JUNK = re.compile(r"[\s\-().‎‏/]")
_ID_JUNK = re.compile(r"[\s\-./‎‏]")


def _ascii_digits(value: str) -> str:
    return value.translate(_ARABIC_DIGITS)


def name(value: object) -> str:
    """Case-folded, Arabic-folded name: NFKC, no diacritics/tatweel, alef/ya/ta-marbuta unified, one space."""
    text = unicodedata.normalize("NFKC", _ascii_digits(str(value or "")))
    text = _DIACRITICS.sub("", text).translate(_LETTER_FOLD).casefold()
    return _SPACES.sub(" ", text).strip()


def email(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


def phone(value: object, default_country: str = "966") -> str:
    """Digits with the country code kept: `+966 50 000 0000`, `00966500000000`, `0500000000`, `500000000` and
    `966500000000` all give `966500000000` (Saudi numbers; `default_country` is prefixed to a national number
    only when it looks like one). Other countries' `+` / `00` numbers keep their own code."""
    text = _PHONE_JUNK.sub("", _ascii_digits(str(value or "")))
    international = text.startswith("+") or text.startswith("00")
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    if text.startswith("00"):
        digits = digits[2:]
    if international:
        return digits
    if digits.startswith(default_country):
        return digits
    if digits.startswith("0"):
        return default_country + digits.lstrip("0")
    if len(digits) == 9 and default_country == "966" and digits.startswith("5"):
        return default_country + digits
    return digits  # a bare number we cannot place -- compared as typed


def phone_variants(value: object, default_country: str = "966") -> list[str]:
    """Plausible stored spellings of a phone number, for index-friendly exact lookups."""
    key = phone(value, default_country)
    if not key:
        return []
    variants = {str(value).strip(), key, "+" + key, "00" + key}
    if key.startswith(default_country):
        national = key[len(default_country):]
        variants.update({national, "0" + national})
    return sorted(v for v in variants if v)


def tax_id(value: object) -> str:
    """VAT / CR / registration numbers: ASCII digits, no separators, upper-case letters kept."""
    return _ID_JUNK.sub("", _ascii_digits(str(value or ""))).upper()


def code(value: object) -> str:
    """Product codes / barcodes: trimmed only -- every character is meaningful (case is left to the column's collation)."""
    return str(value or "").strip()


def text(value: object) -> str:
    return name(value)


KINDS = {"Name": name, "Email": email, "Phone": phone, "Tax ID": tax_id, "Code": code, "Text": text}


def normalize(kind: str, value: object) -> str:
    return KINDS.get(kind, text)(value)


def similarity(a: str, b: str) -> float:
    """0..1 fuzzy ratio of two already-normalised names: character ratio, or token-set overlap if higher."""
    from difflib import SequenceMatcher

    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    if ta and tb:
        ratio = max(ratio, len(ta & tb) / len(ta | tb))
    return ratio
