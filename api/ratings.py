"""Editorial rating and security status — single source of truth (backend).

Thresholds must stay in sync with frontend `src/lib/toolRating.ts`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union

Number = Union[int, float, Decimal]

RATING_MIN_PROVISIONAL = 6
RATING_FULL = 10
SECURITY_VERIFIED_MIN = 12  # out of 20 for the Security & Data Privacy criterion

RATING_NOT_YET_RATED = "NOT_YET_RATED"
RATING_PROVISIONAL = "PROVISIONAL"
RATING_RATED = "RATED"

SECURITY_NOT_ASSESSED = "NOT_ASSESSED"
SECURITY_FLAGGED = "FLAGGED"
SECURITY_VERIFIED = "VERIFIED"

TIER_LABELS = (
    (Decimal("4.50"), "Outstanding"),
    (Decimal("4.00"), "Excellent"),
    (Decimal("3.50"), "Strong"),
    (Decimal("3.00"), "Good"),
    (Decimal("2.00"), "Fair"),
)


def get_rating_status(criteria_completed: Optional[int]) -> str:
    completed = int(criteria_completed or 0)
    if completed < RATING_MIN_PROVISIONAL:
        return RATING_NOT_YET_RATED
    if completed < RATING_FULL:
        return RATING_PROVISIONAL
    return RATING_RATED


def get_security_status(security_criterion_score: Optional[Number]) -> str:
    if security_criterion_score is None:
        return SECURITY_NOT_ASSESSED
    if Decimal(str(security_criterion_score)) < SECURITY_VERIFIED_MIN:
        return SECURITY_FLAGGED
    return SECURITY_VERIFIED


def get_tier_label(score: Optional[Number]) -> Optional[str]:
    if score is None:
        return None
    value = Decimal(str(score))
    for threshold, label in TIER_LABELS:
        if value >= threshold:
            return label
    return "Needs Improvement"


def coerce_overall_score(
    criteria_completed: Optional[int], overall_score: Optional[Number]
) -> Optional[Decimal]:
    """Never persist a numeric score below the provisional threshold."""
    if get_rating_status(criteria_completed) == RATING_NOT_YET_RATED:
        return None
    if overall_score is None:
        return None
    value = Decimal(str(overall_score))
    if value < 0:
        return Decimal("0")
    if value > 5:
        return Decimal("5.00")
    return value.quantize(Decimal("0.01"))
