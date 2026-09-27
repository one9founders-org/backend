"""Directory filters and ordering applied before pagination."""

from __future__ import annotations

from django.db.models import Case, IntegerField, Q, Value, When

ALLOWED_ORDER_FIELDS = {
    "name",
    "created_at",
    "updated_at",
    "rating",
    "overall_score",
    "views_count",
    "popularity_score",
    "display_order",
    "review_count",
}

JOB_CLUSTER_TERMS = {
    "performance-marketing": [
        "performance marketing",
        "advertising",
        "ads",
        "seo",
        "marketing",
    ],
    "sales": ["sales", "crm", "outbound", "lead"],
    "support": ["support", "helpdesk", "customer service", "customer support"],
    "product": ["product management", "roadmap", "product"],
    "engineering": ["engineering", "developer", "code", "devops"],
    "operations": ["operations", "workflow", "ops"],
}


def _text_match(term: str) -> Q:
    return (
        Q(name__icontains=term)
        | Q(short_description__icontains=term)
        | Q(description__icontains=term)
        | Q(tags__icontains=term)
        | Q(use_cases__icontains=term)
        | Q(categories__name__icontains=term)
        | Q(categories__slug__icontains=term)
    )


def apply_directory_query(queryset, params):
    """Filter and order a publishable tool queryset. Caller paginates."""
    q = (params.get("q") or params.get("search") or "").strip()
    if q:
        queryset = queryset.filter(_text_match(q))

    jobs = [
        part.strip()
        for part in (params.get("job_cluster") or params.get("job") or "").split(",")
        if part.strip()
    ]
    if jobs:
        job_q = Q()
        for job in jobs:
            terms = JOB_CLUSTER_TERMS.get(job, [job.replace("-", " ")])
            for term in terms:
                job_q |= _text_match(term)
        queryset = queryset.filter(job_q)

    deployment = (params.get("deployment") or "").strip()
    if deployment:
        queryset = queryset.filter(
            Q(platforms__icontains=deployment) | Q(tags__icontains=deployment)
        )

    integration = (params.get("integration") or "").strip()
    if integration:
        queryset = queryset.filter(integrations__icontains=integration)

    ordering = (params.get("ordering") or "").strip()
    relevance_requested = ordering in {"", "relevance"} or ordering == "match"
    if q and relevance_requested:
        queryset = queryset.annotate(
            _relevance=Case(
                When(name__iexact=q, then=Value(0)),
                When(name__istartswith=q, then=Value(1)),
                When(name__icontains=q, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        ).order_by("_relevance", "name", "id")
        return queryset

    expressions = _ordering_expressions(ordering)
    if expressions:
        return queryset.order_by(*expressions)
    if q:
        return queryset.order_by("name", "id")
    return queryset


def _ordering_expressions(raw: str) -> list:
    if not raw or raw in {"relevance", "match"}:
        return []
    fields = []
    for part in raw.split(","):
        name = part.strip()
        if not name:
            continue
        descending = name.startswith("-")
        field = name[1:] if descending else name
        if field not in ALLOWED_ORDER_FIELDS:
            continue
        if field == "overall_score":
            from django.db.models import F

            expr = F("overall_score")
            fields.append(
                expr.desc(nulls_last=True) if descending else expr.asc(nulls_last=True)
            )
        else:
            fields.append(name)
    return fields
