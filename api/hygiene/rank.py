"""Score tools so the directory can surface genuinely popular ones.

The database has no usable popularity signal today -- 99.8% of rows have
zero reviews and 87% have zero views -- so ranking cannot be derived from
first-party data alone yet. This blends an external footprint signal with
whatever first-party engagement exists, and degrades gracefully as real
click data accumulates.
"""

from dataclasses import dataclass, field

from . import RANK_WEIGHTS

# Fields whose presence means the row is actually useful to a visitor.
COMPLETENESS_FIELDS = (
    "short_description",
    "description",
    "logo_url",
    "website",
    "tags",
    "use_cases",
    "pricing_type",
    "features",
)


@dataclass
class RankInputs:
    external_score: float = 0.0  # 0..1, from websearch.search_footprint_score
    clicks: int = 0
    views: int = 0
    completeness: float = 0.0  # 0..1
    penalties: list[str] = field(default_factory=list)


def completeness_score(tool_data: dict) -> float:
    """Fraction of the fields a visitor actually reads that are populated."""
    filled = 0
    for field_name in COMPLETENESS_FIELDS:
        value = tool_data.get(field_name)
        if value not in (None, "", [], {}, "0.00"):
            filled += 1
    return round(filled / len(COMPLETENESS_FIELDS), 4)


def _engagement_score(clicks: int, views: int) -> float:
    """Compress raw counts so a handful of clicks cannot dominate."""
    weighted = (clicks or 0) * 3 + (views or 0)
    if weighted <= 0:
        return 0.0
    # Saturating curve: 100 weighted actions ~= 0.5, 1000 ~= 0.83.
    return round(weighted / (weighted + 100.0), 4)


def score(inputs: RankInputs) -> float:
    """Final 0..1 popularity score."""
    parts = {
        "external": max(0.0, min(inputs.external_score, 1.0)),
        "search": max(0.0, min(inputs.external_score, 1.0)),
        "engagement": _engagement_score(inputs.clicks, inputs.views),
        "completeness": max(0.0, min(inputs.completeness, 1.0)),
    }
    total = sum(parts[key] * weight for key, weight in RANK_WEIGHTS.items())

    # A broken link makes a tool worthless to a visitor no matter how
    # popular it is elsewhere.
    if "broken_link" in inputs.penalties:
        total *= 0.25
    if "not_publishable" in inputs.penalties:
        total *= 0.10

    return round(max(0.0, min(total, 1.0)), 4)


def display_order_for(rank_score: float) -> int:
    """Map score onto the existing display_order field (lower = higher)."""
    return max(1, int(round((1.0 - rank_score) * 9998)) + 1)
