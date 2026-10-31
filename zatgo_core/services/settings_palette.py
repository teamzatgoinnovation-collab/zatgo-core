"""Colour tokens of the Settings Map, derived from one accent per app (manifest key `color`).

Pure python, no database: the catalog validates colours with it and the page receives exactly what
`palette()` returns, so tests/unit/test_settings_map.py proves the contrast of what ships (WCAG 2.x, >= 4.5:1 for text).

  accent       the manifest colour; fills (switch, pills, icon tile) carry white text (`on_accent`)
  tint         the accent at 12% over a white card; background of soft pills
  ink          accent text on the white card and on `tint`
  dark         the same four tokens for the dark card, where the accent is lightened
"""

from __future__ import annotations

import re

WHITE = "#FFFFFF"
BLACK = "#0B1020"
DARK_CARD = "#1C2230"
MIN_CONTRAST = 4.5
DEFAULT_COLOR = "#475569"

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def is_hex(value: object) -> bool:
    return isinstance(value, str) and bool(_HEX.match(value))


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


def mix(a: str, b: str, weight_b: float) -> str:
    """`a` blended with `b` (weight_b = share of b, 0..1)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x * (1 - weight_b) + y * weight_b for x, y in zip(ra, rb)))


def luminance(hex_color: str) -> float:
    def lin(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _toward(color: str, target: str, backgrounds: tuple[str, ...]) -> str:
    """Move `color` toward `target` in 4% steps until it reaches 4.5:1 on every background."""
    for step in range(0, 26):
        candidate = mix(color, target, step * 0.04)
        if all(contrast(candidate, bg) >= MIN_CONTRAST for bg in backgrounds):
            return candidate
    return target


def palette(accent: str) -> dict[str, dict[str, str] | str]:
    """Light and dark tokens for one accent."""
    if not is_hex(accent):
        accent = DEFAULT_COLOR
    accent = accent.upper()
    tint = mix(WHITE, accent, 0.12)
    ink = _toward(accent, BLACK, (WHITE, tint))
    on_accent = WHITE if contrast(accent, WHITE) >= MIN_CONTRAST else BLACK
    d_accent, d_tint = WHITE, mix(DARK_CARD, WHITE, 0.16)
    for step in range(0, 26):  # the tint follows the accent, so test the pair together
        d_accent = mix(accent, WHITE, step * 0.04)
        d_tint = mix(DARK_CARD, d_accent, 0.16)
        if contrast(d_accent, DARK_CARD) >= MIN_CONTRAST and contrast(d_accent, d_tint) >= MIN_CONTRAST:
            break
    d_on = BLACK if contrast(d_accent, BLACK) >= contrast(d_accent, WHITE) else WHITE
    return {
        "accent": accent,
        "on_accent": on_accent,
        "tint": tint,
        "ink": ink,
        "dark": {"accent": d_accent, "on_accent": d_on, "tint": d_tint, "ink": d_accent, "card": DARK_CARD},
    }
