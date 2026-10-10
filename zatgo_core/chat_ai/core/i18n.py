"""Chat language metadata (English, Arabic, Malayalam) — no Frappe imports."""

from __future__ import annotations

LANGUAGES: dict[str, dict[str, str]] = {
	"en": {
		"code": "en",
		"label": "English",
		"native": "English",
		"bcp47": "en-US",
		"dir": "ltr",
		"prompt": (
			"Reply in clear, natural English — like a helpful coworker speaking, not a formal report. "
			"Unless the user explicitly asks for another language."
		),
	},
	"ar": {
		"code": "ar",
		"label": "Arabic",
		"native": "العربية",
		"bcp47": "ar-SA",
		"dir": "rtl",
		"prompt": (
			"Always reply in natural Modern Standard Arabic (العربية الفصحى) as a helpful coworker would speak, "
			"unless the user asks otherwise. Keep DocType and field names in English when referring to ERPNext."
		),
	},
	"ml": {
		"code": "ml",
		"label": "Malayalam",
		"native": "മലയാളം",
		"bcp47": "ml-IN",
		"dir": "ltr",
		"prompt": (
			"Always reply in natural Malayalam (മലയാളം) as a helpful coworker would speak, "
			"unless the user asks otherwise. Keep DocType and field names in English when referring to ERPNext."
		),
	},
}


def normalize_language(value: str | None) -> str:
	raw = (value or "").strip().lower()
	if not raw or raw in ("auto", "default"):
		return "en"
	# Accept labels / locales
	aliases = {
		"english": "en",
		"en-us": "en",
		"en-gb": "en",
		"arabic": "ar",
		"ar-sa": "ar",
		"ar-ae": "ar",
		"العربية": "ar",
		"malayalam": "ml",
		"ml-in": "ml",
		"മലയാളം": "ml",
	}
	if raw in LANGUAGES:
		return raw
	return aliases.get(raw, raw.split("-")[0] if raw.split("-")[0] in LANGUAGES else "en")


def get_language(code: str | None) -> dict[str, str]:
	return LANGUAGES[normalize_language(code)]


def language_prompt(code: str | None) -> str:
	return get_language(code)["prompt"]


def select_options() -> str:
	"""DocType Select options string."""
	return "\n".join(f"{meta['code']}\n{meta['label']}" for meta in LANGUAGES.values())
