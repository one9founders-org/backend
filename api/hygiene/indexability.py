"""Which publishable tools belong in the public sitemap / should be indexed.

Mirrors frontend `src/lib/tool-content.ts` `isToolIndexable()` so the XML
sitemap and page `robots` meta stay aligned. Thin stubs stay publishable
(directory / HN catalogue) but are omitted from the sitemap and remain
noindex on the page.
"""

from __future__ import annotations

from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce, Length

from api.ratings import RATING_MIN_PROVISIONAL

from .visibility import publishable_queryset

# ~40 words ≈ 200 characters; ~15 words ≈ 75 characters.
MIN_DESCRIPTION_CHARS = 200
MIN_CATALOGUE_CHARS = 75


def _non_empty_json_list(field: str) -> Q:
    """True when a JSON list field has at least one entry."""
    return ~Q(**{field: []}) & ~Q(**{f"{field}__isnull": True})


def indexable_q() -> Q:
    """SQL form of isToolIndexable (length proxy for word counts)."""
    assessed = Q(criteria_completed__gte=RATING_MIN_PROVISIONAL)

    secondary = (
        _non_empty_json_list("pricing_models")
        | _non_empty_json_list("use_cases")
        | Q(pricing_from__isnull=False)
        | (
            Q(pricing_type__isnull=False)
            & ~Q(pricing_type="")
            & ~Q(pricing_type__iexact="n/a")
            & ~Q(pricing_type__iexact="coming soon")
        )
    )
    substantive = Q(_desc_len__gte=MIN_DESCRIPTION_CHARS) & secondary

    hn = Q(tags__contains=["hackernews"]) | Q(sources__source="hackernews")
    catalogue_signal = (
        (Q(website__isnull=False) & ~Q(website=""))
        | _non_empty_json_list("pricing_models")
        | (
            Q(pricing_type__isnull=False)
            & ~Q(pricing_type="")
            & ~Q(pricing_type__iexact="n/a")
        )
        | _non_empty_json_list("use_cases")
    )
    catalogue = hn & Q(_combined_len__gte=MIN_CATALOGUE_CHARS) & catalogue_signal

    return assessed | substantive | catalogue


def indexable_queryset(qs=None):
    """Publishable tools that should appear in the sitemap."""
    if qs is None:
        qs = publishable_queryset()
    return (
        qs.annotate(
            _desc_len=Length(Coalesce("description", Value(""))),
            _short_len=Length(Coalesce("short_description", Value(""))),
        )
        .annotate(_combined_len=F("_desc_len") + F("_short_len"))
        .filter(indexable_q())
        .distinct()
    )
