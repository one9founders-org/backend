"""Automated publish gate. All failure reasons are returned together."""

from difflib import SequenceMatcher

from . import (
    MAX_DESCRIPTION_WORDS,
    MIN_DESCRIPTION_WORDS,
    SIMILARITY_REJECT_RATIO,
)
from .facts import Facts


def word_count(text: str) -> int:
    return len((text or "").split())


def similarity_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def passes_quality_gate(
    tool_name: str,
    generated: str,
    facts: Facts,
    source_text: str,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    words = word_count(generated)
    if words < MIN_DESCRIPTION_WORDS:
        reasons.append(f"word count {words} is under {MIN_DESCRIPTION_WORDS}")
    if words > MAX_DESCRIPTION_WORDS:
        reasons.append(f"word count {words} is over {MAX_DESCRIPTION_WORDS}")

    ratio = similarity_ratio(generated, source_text)
    if source_text and ratio > SIMILARITY_REJECT_RATIO:
        reasons.append(
            "description too similar to source "
            f"(ratio={ratio:.2f} > {SIMILARITY_REJECT_RATIO})"
        )

    if not facts.pricing and not facts.category:
        reasons.append("pricing and category are both missing")

    if not (generated or "").strip():
        reasons.append("generated description is empty")
    if not (tool_name or "").strip():
        reasons.append("tool name is empty")

    return (len(reasons) == 0, reasons)
