from __future__ import annotations

import unicodedata

_WIDE_VOWELS = {"ㅏ", "ㅑ", "ㅐ", "ㅒ", "ㅓ", "ㅕ", "ㅔ", "ㅖ"}
_ROUND_VOWELS = {"ㅗ", "ㅛ", "ㅜ", "ㅠ", "ㅚ", "ㅟ", "ㅘ", "ㅙ", "ㅝ", "ㅞ"}
_NARROW_VOWELS = {"ㅡ", "ㅣ", "ㅢ"}
_PAUSE = set(" \t\r\n,.;:!?…—-()[]{}\"'·")


def _hangul_vowel(ch: str) -> str | None:
    if not ch:
        return None
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        medial = ((code - 0xAC00) // 28) % 21
        return (
            "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ", "ㅙ",
            "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ",
        )[medial]
    name = unicodedata.name(ch, "")
    if "HANGUL LETTER" in name:
        return ch
    return None


def shape_for_character(ch: str) -> str:
    if not ch or ch in _PAUSE:
        return "closed"
    vowel = _hangul_vowel(ch)
    if vowel in _WIDE_VOWELS:
        return "wide"
    if vowel in _ROUND_VOWELS:
        return "round"
    if vowel in _NARROW_VOWELS:
        return "narrow"
    return "open"


def viseme_shape(text: str, progress: float, amplitude: float = 0.0) -> str:
    if not text:
        return "closed"
    progress = max(0.0, min(1.0, progress))
    if progress < 0.025 or progress > 0.985 or amplitude <= 0.012:
        return "closed"
    idx = min(len(text) - 1, int(progress * len(text)))
    shape = shape_for_character(text[idx])
    if shape == "closed":
        return shape
    if amplitude > 0.64 and shape in {"open", "wide"}:
        return "wide"
    return shape
