"""Crawl published vendor pages with Firecrawl and score the six fintech checks.

Pass and Fail must quote a crawled page. Unknown is the default. We never
write Tool.overall_score or assessment_detail.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.utils import timezone
from openai import OpenAI, OpenAIError

from .fintech import CHECKS, ensure_checks
from .fintech_catalog import CatalogVendor, vendors_for
from .firecrawl import FirecrawlClient, FirecrawlError, ScrapedPage
from .models import FintechEvidencePage, FintechRating, Tool

logger = logging.getLogger(__name__)

CHECK_SLUGS = [spec["slug"] for spec in CHECKS]
PAGE_CAP_CHARS = 20_000
PAGE_PROMPT_CHARS = 4_000
STALE_DAYS = 14
DEFAULT_MAX_PAGES = 8

SKIP_URL_BITS = (
    "/career",
    "/jobs",
    "/login",
    "/signup",
    "/signin",
    "/cart",
    "/wp-json",
    "/tag/",
    "/author/",
    "/cdn-cgi/",
    "linkedin.com",
    "twitter.com",
    "x.com/",
    "facebook.com",
    "youtube.com",
)

URL_WEIGHTS = (
    ("privacy", 12),
    ("trust", 11),
    ("security", 11),
    ("compliance", 10),
    ("dpdpa", 10),
    ("dpdp", 10),
    ("residenc", 10),
    ("locali", 10),
    ("consent", 9),
    ("rbi", 8),
    ("about", 7),
    ("legal", 5),
    ("certif", 6),
    ("iso", 5),
    ("soc", 5),
    ("gdpr", 5),
    ("explain", 6),
    ("bias", 6),
    ("fair", 4),
    ("kyc", 5),
    ("aml", 5),
    ("india", 3),
)

SYSTEM_PROMPT = """You score Indian-fintech AI vendors from published pages only.

You will receive markdown from pages we crawled, each tagged with its URL.
Use ONLY that text. You have no other knowledge of the vendor.

For each of the six checks, result is pass, fail, or unknown.
- pass: a crawled page explicitly supports the check.
- fail: a crawled page explicitly contradicts the check.
- unknown: the pages do not clearly support or contradict it. Unknown is expected.

Rules:
- Marketing slogans are not evidence.
- "We comply with RBI" without a named residency, consent, or
  explainability claim is unknown.
- A privacy-policy "contact us to withdraw consent" as a processor
  is not a DPDP consent-manager product.
- SOC / ISO / PCI: pass only if a page names the cert. Do not invent Type II.
- Bias: a fairness slogan is unknown unless they publish a test,
  audit, or disparate-impact study.
- Vendor viability: funding, MCA/CIN, named HQ, or a dated customer
  win on their domain.

For pass or fail you MUST set evidence_url to exactly one crawled URL and quote a
substring that appears on that page (copy-paste, not paraphrased). If you cannot
quote a crawled page, the result is unknown and evidence_url is empty.

Return a single JSON object, no prose around it."""


@dataclass
class VendorOutcome:
    slug: str
    name: str
    skipped: str = ""
    error: str = ""
    pages: int = 0
    wrote: bool = False
    results: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def host_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def same_site(candidate: str, homepage: str) -> bool:
    left = host_of(candidate)
    right = host_of(homepage)
    if not left or not right:
        return False
    return left == right or left.endswith("." + right)


def url_score(url: str, title: str = "") -> int:
    blob = f"{url} {title}".lower()
    if any(bit in blob for bit in SKIP_URL_BITS):
        return -1
    score = 0
    for needle, weight in URL_WEIGHTS:
        if needle in blob:
            score += weight
    return score


def pick_urls(
    homepage: str,
    mapped: list,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[str]:
    """Homepage first, then the highest-scoring same-site URLs."""
    ranked: list[tuple[int, str]] = []
    seen = {homepage.rstrip("/").lower()}
    for item in mapped:
        url = item.url if hasattr(item, "url") else str(item)
        title = getattr(item, "title", "") if hasattr(item, "title") else ""
        url = url.strip()
        if not url or not same_site(url, homepage):
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        score = url_score(url, title)
        if score < 0:
            continue
        seen.add(key)
        ranked.append((score, url))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    picked = [homepage]
    for _score, url in ranked:
        if len(picked) >= max_pages:
            break
        picked.append(url)
    return picked


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def quote_supported(quote: str, markdown: str) -> bool:
    q = _normalize_text(quote)
    if len(q) < 12:
        return False
    return q in _normalize_text(markdown)


def coerce_scores(raw_checks, pages_by_url: dict[str, str]) -> list[dict]:
    by_id = {}
    if isinstance(raw_checks, list):
        for row in raw_checks:
            if isinstance(row, dict) and row.get("id"):
                by_id[str(row["id"])] = row

    allowed_urls = {url.rstrip("/").lower(): url for url in pages_by_url}
    out = []
    for slug in CHECK_SLUGS:
        row = by_id.get(slug) or {}
        result = str(row.get("result") or "unknown").strip().lower()
        if result not in {"pass", "fail", "unknown"}:
            result = "unknown"
        rationale = str(row.get("rationale") or "").strip()
        evidence_url = str(row.get("evidence_url") or "").strip()
        evidence_label = str(row.get("evidence_label") or "").strip()
        quote = str(row.get("quote") or "").strip()

        if result in {"pass", "fail"}:
            matched = allowed_urls.get(evidence_url.rstrip("/").lower())
            if not matched:
                evid_path = urlparse(evidence_url).path.rstrip("/").lower()
                for url in pages_by_url:
                    if urlparse(url).path.rstrip("/").lower() == evid_path:
                        matched = url
                        break
            page_md = pages_by_url.get(matched or "", "")
            if not matched or not quote_supported(quote, page_md):
                result = "unknown"
                evidence_url = ""
                evidence_label = ""
                if not rationale:
                    rationale = (
                        "No quoted published page supported this check, "
                        "so it is Unknown."
                    )
            else:
                evidence_url = matched
        else:
            evidence_url = ""
            evidence_label = ""
            if not rationale:
                rationale = "No published page found for this check."

        out.append(
            {
                "check": slug,
                "result": result,
                "rationale": rationale[:500],
                "evidence_url": evidence_url,
                "evidence_label": evidence_label[:160],
            }
        )
    return out


def _client() -> OpenAI:
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _model_name() -> str:
    return getattr(settings, "HYGIENE_ASSESS_MODEL", "gpt-4o-mini")


def score_from_pages(
    vendor: CatalogVendor,
    pages: list[ScrapedPage],
) -> dict:
    payload = {
        "vendor": vendor.name,
        "website": vendor.website,
        "stack": vendor.stack,
        "checks": CHECKS,
        "pages": [
            {
                "url": page.url,
                "title": page.title,
                "markdown": (page.markdown or "")[:PAGE_PROMPT_CHARS],
            }
            for page in pages
        ],
        "response_shape": {
            "short_description": "string, max 160 characters, what the product does",
            "india_relevance": "string, max 320 characters, only if a page supports it",
            "checks": [
                {
                    "id": "one of the six check slugs",
                    "result": "pass | fail | unknown",
                    "rationale": "string, max 400 characters",
                    "evidence_url": "crawled URL or empty",
                    "evidence_label": "short page name",
                    "quote": "verbatim substring from that page",
                }
            ],
        },
    }
    try:
        response = _client().chat.completions.create(
            model=_model_name(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=1400,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except (OpenAIError, json.JSONDecodeError, IndexError, TypeError) as exc:
        logger.warning("Fintech score failed for %s: %s", vendor.slug, exc)
        data = {}
    pages_by_url = {page.url: page.markdown or "" for page in pages}
    checks = coerce_scores(data.get("checks"), pages_by_url)
    short = str(data.get("short_description") or vendor.one_liner).strip()
    india = str(data.get("india_relevance") or vendor.india_relevance).strip()
    return {
        "short_description": (short or vendor.one_liner)[:200],
        "india_relevance": (india or vendor.india_relevance)[:400],
        "checks": checks,
    }


def _get_or_create_tool(vendor: CatalogVendor) -> Tool:
    tool = Tool.objects.filter(slug=vendor.slug).first()
    if tool is None:
        host = host_of(vendor.website)
        for candidate in Tool.objects.filter(name=vendor.name):
            if host_of(candidate.website or "") == host:
                tool = candidate
                break
    if tool is None:
        tool = Tool(
            slug=vendor.slug,
            name=vendor.name,
            description=vendor.one_liner,
            short_description=vendor.one_liner[:200],
            website=vendor.website,
            startup_benefits=vendor.india_relevance,
            is_active=True,
            is_featured=False,
            tags=["fintech", vendor.stack],
        )
        tool.save()
        return tool
    updates = []
    if not tool.website:
        tool.website = vendor.website
        updates.append("website")
    if not tool.startup_benefits:
        tool.startup_benefits = vendor.india_relevance
        updates.append("startup_benefits")
    tags = list(tool.tags or [])
    for tag in ("fintech", vendor.stack):
        if tag not in tags:
            tags.append(tag)
    if tags != list(tool.tags or []):
        tool.tags = tags
        updates.append("tags")
    if updates:
        tool.save(update_fields=updates)
    return tool


def _store_pages(tool: Tool, pages: list[ScrapedPage]) -> int:
    now = timezone.now()
    stored = 0
    for page in pages:
        markdown = (page.markdown or "")[:PAGE_CAP_CHARS]
        if not markdown.strip():
            continue
        FintechEvidencePage.objects.update_or_create(
            tool=tool,
            url=page.url[:500],
            defaults={
                "title": (page.title or "")[:300],
                "markdown": markdown,
                "crawled_at": now,
            },
        )
        stored += 1
    return stored


def _pages_from_db(tool: Tool) -> list[ScrapedPage]:
    cutoff = timezone.now() - timedelta(days=STALE_DAYS)
    rows = FintechEvidencePage.objects.filter(tool=tool, crawled_at__gte=cutoff)
    return [
        ScrapedPage(url=row.url, title=row.title, markdown=row.markdown)
        for row in rows
        if (row.markdown or "").strip()
    ]


def _write_ratings(
    tool: Tool, vendor: CatalogVendor, scored: dict, reviewed_at
) -> None:
    checks = ensure_checks()
    india = scored["india_relevance"][:400]
    for row in scored["checks"]:
        obj, _ = FintechRating.objects.update_or_create(
            tool=tool,
            criterion=checks[row["check"]],
            stack=vendor.stack,
            defaults={
                "result": row["result"],
                "rationale": row["rationale"],
                "evidence_url": row["evidence_url"],
                "evidence_label": row["evidence_label"],
                "reviewed_at": reviewed_at,
                "india_relevance": india,
            },
        )
        obj.full_clean()
    short = scored["short_description"][:200]
    if short and (
        not tool.short_description or tool.short_description == vendor.one_liner[:200]
    ):
        tool.short_description = short
        tool.save(update_fields=["short_description"])


def _already_rated(vendor: CatalogVendor) -> bool:
    tool = Tool.objects.filter(slug=vendor.slug).first()
    if tool is None:
        return False
    return FintechRating.objects.filter(tool=tool, stack=vendor.stack).count() >= len(
        CHECK_SLUGS
    )


def fetch_pages(
    vendor: CatalogVendor,
    client: FirecrawlClient,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> list[ScrapedPage]:
    mapped = client.map(vendor.website)
    urls = pick_urls(vendor.website, mapped, max_pages=max_pages)
    pages: list[ScrapedPage] = []
    for url in urls:
        try:
            page = client.scrape(url)
        except FirecrawlError as exc:
            logger.warning("Scrape failed %s %s: %s", vendor.slug, url, exc)
            continue
        if not (page.markdown or "").strip():
            continue
        # Keep the URL we asked for so evidence_url matches the catalog site.
        page.url = urljoin(vendor.website, urlparse(url).path or "/")
        if url.rstrip("/") == vendor.website.rstrip("/"):
            page.url = vendor.website
        pages.append(page)
    return pages


def ingest_vendor(
    vendor: CatalogVendor,
    *,
    client: FirecrawlClient | None = None,
    score_fn=score_from_pages,
    fetch: bool = False,
    apply: bool = False,
    rescore_only: bool = False,
    refresh: bool = False,
    overwrite_reviewed: bool = False,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> VendorOutcome:
    outcome = VendorOutcome(slug=vendor.slug, name=vendor.name)
    if vendor.hand_reviewed and not overwrite_reviewed:
        outcome.skipped = "hand_reviewed"
        return outcome
    if not refresh and _already_rated(vendor):
        outcome.skipped = "already_rated"
        return outcome

    pages: list[ScrapedPage] = []
    tool = Tool.objects.filter(slug=vendor.slug).first()
    if rescore_only:
        if tool is None:
            outcome.skipped = "no_stored_pages"
            return outcome
        pages = _pages_from_db(tool)
        if not pages:
            outcome.skipped = "no_stored_pages"
            return outcome
    elif fetch:
        client = client or FirecrawlClient()
        try:
            pages = fetch_pages(vendor, client, max_pages=max_pages)
        except FirecrawlError as exc:
            outcome.error = str(exc)
            return outcome
        if not pages:
            outcome.error = "no_pages_crawled"
            return outcome
    else:
        outcome.skipped = "plan_only"
        outcome.notes.append(f"estimate {1 + max_pages} Firecrawl credits")
        return outcome

    outcome.pages = len(pages)
    scored = score_fn(vendor, pages)
    outcome.results = {row["check"]: row["result"] for row in scored["checks"]}
    if not apply:
        outcome.notes.append("dry_run")
        return outcome

    tool = _get_or_create_tool(vendor)
    if fetch:
        _store_pages(tool, pages)
    _write_ratings(tool, vendor, scored, reviewed_at=timezone.now().date())
    outcome.wrote = True
    return outcome


def run(
    *,
    stack: str = "all",
    slug: str | None = None,
    fetch: bool = False,
    apply: bool = False,
    rescore_only: bool = False,
    refresh: bool = False,
    overwrite_reviewed: bool = False,
    limit: int = 0,
    max_pages: int = DEFAULT_MAX_PAGES,
    client: FirecrawlClient | None = None,
    score_fn=score_from_pages,
) -> dict:
    selected = vendors_for(stack=stack, slug=slug)
    if limit and limit > 0:
        selected = selected[:limit]
    outcomes = [
        ingest_vendor(
            vendor,
            client=client,
            score_fn=score_fn,
            fetch=fetch,
            apply=apply,
            rescore_only=rescore_only,
            refresh=refresh,
            overwrite_reviewed=overwrite_reviewed,
            max_pages=max_pages,
        )
        for vendor in selected
    ]
    return {
        "stack": stack,
        "count": len(selected),
        "wrote": sum(1 for row in outcomes if row.wrote),
        "skipped": sum(1 for row in outcomes if row.skipped),
        "errors": sum(1 for row in outcomes if row.error),
        "estimated_credits": sum(
            1 + max_pages for row in outcomes if row.skipped == "plan_only"
        ),
        "outcomes": outcomes,
    }
