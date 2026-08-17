"""Upsert scraped agent candidates into AIAgent / AgentCategory."""

import logging
from datetime import timedelta

from django.utils import timezone
from django.utils.text import slugify

from agents.discovery import SOURCE_RANK
from agents.discovery.normalize import (
    label_to_slug,
    normalize_name,
    normalize_url,
    unique_slug,
)
from agents.models import AgentCategory, AIAgent

logger = logging.getLogger(__name__)

UPDATE_FIELDS = [
    "external_id",
    "name",
    "category",
    "category_name",
    "industry",
    "access",
    "pricing_model",
    "short_description",
    "long_description",
    "key_features",
    "use_cases",
    "logo_url",
    "image_url",
    "video_url",
    "popularity_score",
    "upvotes",
    "views",
    "website",
    "github_url",
    "twitter_url",
    "linkedin_url",
    "discord_url",
    "email",
    "is_featured",
    "source",
    "created_at",
]


def _is_empty(value) -> bool:
    if isinstance(value, bool):
        return False
    return value in (None, "", [], 0, 0.0)


def ensure_categories(labels: list[str]) -> dict[str, AgentCategory]:
    lookup = {c.slug: c for c in AgentCategory.objects.all()}
    to_create = []
    for label in labels:
        slug = label_to_slug(label)
        if not slug or slug in lookup:
            continue
        category = AgentCategory(slug=slug, label=label.strip())
        to_create.append(category)
        lookup[slug] = category
    if to_create:
        AgentCategory.objects.bulk_create(to_create, batch_size=200)
        lookup = {c.slug: c for c in AgentCategory.objects.all()}
    return lookup


def _match_existing(candidate: dict, by_slug, by_external, by_url, by_name):
    external_id = candidate.get("external_id")
    if external_id and external_id in by_external:
        return by_external[external_id]
    slug = candidate.get("slug")
    if slug and slug in by_slug:
        return by_slug[slug]
    url_key = normalize_url(candidate.get("website") or "")
    if url_key and url_key in by_url:
        return by_url[url_key]
    name_key = normalize_name(candidate.get("name") or "")
    if name_key and len(name_key) >= 4 and name_key in by_name:
        return by_name[name_key]
    return None


def _apply_candidate(
    agent: AIAgent, candidate: dict, category, overwrite: bool
) -> bool:
    incoming_rank = candidate.get("source_rank") or SOURCE_RANK.get(
        candidate.get("source") or "", 0
    )
    existing_rank = SOURCE_RANK.get(agent.source or "", 0)
    stronger = overwrite or incoming_rank > existing_rank

    mapping = {
        "external_id": candidate.get("external_id"),
        "name": candidate.get("name") or agent.name,
        "category": category if category is not None else agent.category,
        "category_name": candidate.get("category_label") or agent.category_name,
        "industry": candidate.get("industry") or "",
        "access": candidate.get("access") or "",
        "pricing_model": candidate.get("pricing_model") or "",
        "short_description": candidate.get("short_description") or "",
        "long_description": candidate.get("long_description") or "",
        "key_features": candidate.get("key_features") or [],
        "use_cases": candidate.get("use_cases") or [],
        "logo_url": candidate.get("logo_url") or "",
        "image_url": candidate.get("image_url") or "",
        "video_url": candidate.get("video_url") or "",
        "popularity_score": candidate.get("popularity_score") or 0,
        "upvotes": candidate.get("upvotes") or 0,
        "views": candidate.get("views") or 0,
        "github_url": candidate.get("github_url") or "",
        "twitter_url": candidate.get("twitter_url") or "",
        "linkedin_url": candidate.get("linkedin_url") or "",
        "discord_url": candidate.get("discord_url") or "",
        "email": candidate.get("email") or "",
        "is_featured": bool(candidate.get("is_featured")),
        "source": candidate.get("source") or agent.source,
        "created_at": candidate.get("created_at"),
        "website": candidate.get("website") or agent.website,
    }

    changed = False
    for field, value in mapping.items():
        if field == "created_at" and not value:
            continue
        current = getattr(agent, field)
        if stronger:
            if field == "is_featured" and not overwrite:
                next_value = current or value
            elif _is_empty(value):
                next_value = current
            else:
                next_value = value
        else:
            if field in {
                "source",
                "name",
                "popularity_score",
                "upvotes",
                "views",
                "is_featured",
            }:
                next_value = current
            elif _is_empty(current):
                next_value = value
            else:
                next_value = current
        if current != next_value:
            setattr(agent, field, next_value)
            changed = True
    return changed


def ingest_candidates(candidates: list[dict], *, dry_run: bool = False) -> dict:
    """Create or update AIAgent rows. Higher-ranked sources win on conflicts."""
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.get("source_rank") or 0,
            item.get("popularity_score") or 0,
        ),
        reverse=True,
    )

    labels = [item.get("category_label") or "" for item in ranked]
    cat_lookup = {} if dry_run else ensure_categories(labels)

    existing = list(AIAgent.objects.select_related("category").all())
    by_slug = {agent.slug: agent for agent in existing}
    by_external = {agent.external_id: agent for agent in existing if agent.external_id}
    by_url = {}
    by_name = {}
    for agent in existing:
        url_key = normalize_url(agent.website or "")
        if url_key:
            by_url.setdefault(url_key, agent)
        name_key = normalize_name(agent.name or "")
        if name_key:
            by_name.setdefault(name_key, agent)

    existing_slugs = set(by_slug)
    to_create: list[AIAgent] = []
    to_update: list[AIAgent] = []
    created = updated = skipped = 0
    seen_keys: set[str] = set()
    touched_pks: set[int] = set()

    for candidate in ranked:
        name = candidate.get("name") or ""
        website = candidate.get("website") or ""
        if not name or not website:
            skipped += 1
            continue
        url_key = normalize_url(website)
        name_key = normalize_name(name)
        dupe_key = url_key or name_key
        if dupe_key and dupe_key in seen_keys:
            skipped += 1
            continue
        if dupe_key:
            seen_keys.add(dupe_key)

        agent = _match_existing(candidate, by_slug, by_external, by_url, by_name)
        category = None
        slug = label_to_slug(candidate.get("category_label") or "")
        if slug:
            category = cat_lookup.get(slug)

        if agent:
            if agent.pk and agent.pk in touched_pks:
                skipped += 1
                continue
            overwrite = (candidate.get("source") or "") == (agent.source or "") or (
                (candidate.get("source_rank") or 0)
                > SOURCE_RANK.get(agent.source or "", 0)
            )
            if _apply_candidate(agent, candidate, category, overwrite):
                to_update.append(agent)
                updated += 1
            else:
                skipped += 1
            if agent.pk:
                touched_pks.add(agent.pk)
            continue

        slug_value = candidate.get("slug") or slugify(name) or "agent"
        slug_value = unique_slug(slug_value, existing_slugs)
        agent = AIAgent(
            slug=slug_value,
            website=website,
        )
        _apply_candidate(agent, candidate, category, overwrite=True)
        to_create.append(agent)
        by_slug[slug_value] = agent
        if agent.external_id:
            by_external[agent.external_id] = agent
        if url_key:
            by_url[url_key] = agent
        if name_key:
            by_name[name_key] = agent
        created += 1

    if not dry_run:
        if to_create:
            AIAgent.objects.bulk_create(to_create, batch_size=200)
        if to_update:
            AIAgent.objects.bulk_update(to_update, UPDATE_FIELDS, batch_size=200)
        refresh_category_counts()

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "dry_run": dry_run,
    }


def refresh_category_counts() -> int:
    now = timezone.now()
    cutoff = now - timedelta(days=30)
    categories = list(AgentCategory.objects.all())
    to_update = []
    for category in categories:
        qs = category.agents.all()
        agent_count = qs.count()
        new_30d = qs.filter(created_at__gte=cutoff).count()
        if category.agent_count != agent_count or category.new_agents_30d != new_30d:
            category.agent_count = agent_count
            category.new_agents_30d = new_30d
            to_update.append(category)
    if to_update:
        AgentCategory.objects.bulk_update(
            to_update, ["agent_count", "new_agents_30d"], batch_size=200
        )
    return len(to_update)
