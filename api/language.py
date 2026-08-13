"""English-language lint for tool descriptions.

Flags non-English copy (e.g. scraped French ElevenLabs blurbs) before it goes live.
"""

from __future__ import annotations

import re
from typing import Optional

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ']+")

_ENGLISH_MARKERS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "with",
    "on",
    "is",
    "are",
    "this",
    "that",
    "from",
    "your",
    "you",
    "we",
    "our",
    "it",
    "as",
    "at",
    "by",
    "be",
    "can",
    "ai",
    "tool",
    "tools",
}

_NON_ENGLISH_MARKERS = {
    # French
    "le",
    "la",
    "les",
    "des",
    "du",
    "un",
    "une",
    "et",
    "en",
    "dans",
    "est",
    "sont",
    "que",
    "qui",
    "avec",
    "pour",
    "plus",
    "vous",
    "nous",
    "une",
    "voix",
    "textes",
    "transformez",
    # Spanish
    "el",
    "los",
    "las",
    "una",
    "para",
    "como",
    "más",
    "este",
    "esta",
    # German
    "und",
    "der",
    "die",
    "das",
    "ein",
    "eine",
    "mit",
    "nicht",
    "von",
    "für",
    "ist",
    "sie",
    # Portuguese
    "uma",
    "não",
    "os",
    "as",
    "pelo",
    "pela",
}

# Exact (case-insensitive) scraped strings we already have English replacements for.
KNOWN_ENGLISH_TRANSLATIONS = {
    "transformez des textes en voix ultra réalistes": (
        "Transform text into ultra-realistic speech."
    ),
    "transformez des textes en voix ultra réalistes.": (
        "Transform text into ultra-realistic speech."
    ),
}


def _tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]


def is_english_text(text: Optional[str]) -> bool:
    """Return True when `text` looks like English (or is too short to judge)."""
    if not text or not text.strip():
        return True
    words = _tokens(text)
    if len(words) < 4:
        return True
    english_hits = sum(1 for w in words if w in _ENGLISH_MARKERS)
    foreign_hits = sum(1 for w in words if w in _NON_ENGLISH_MARKERS)
    if foreign_hits >= 2 and foreign_hits > english_hits:
        return False
    if english_hits == 0 and foreign_hits >= 1:
        return False
    return True


def description_needs_review(text: Optional[str]) -> bool:
    return not is_english_text(text)


def known_english_translation(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return KNOWN_ENGLISH_TRANSLATIONS.get(text.strip().lower())
