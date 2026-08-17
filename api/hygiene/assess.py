"""Score tools against the ten published methodology criteria.

The methodology page at /methodology already tells visitors we rate tools
on ten criteria. This module closes as much of that gap as can be closed
honestly: score a criterion only when a citable published page supports
it, and leave the rest unassessed.

Three criteria are never automated. Ease of use and reliability need
someone actually using the product. A full security test would mean
reading terms *and* testing controls — we only score published posture
(HTTPS, a reachable privacy policy, stated SOC 2 / GDPR / DPA /
retention commitments). The words verified, audited, and penetration
tested do not belong in this pass.
"""

import json
import logging
from urllib.parse import urlparse

from django.conf import settings
from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"

# USD per million tokens. Unknown models are priced as gpt-4o so a
# misconfigured env var aborts the budget guard early rather than late.
USD_PER_MILLION = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}
UNKNOWN_MODEL_RATES = (2.50, 10.00)

# id, human name, whether evidence can be gathered without hands-on use.
CRITERIA: tuple[tuple[str, str, bool], ...] = (
    ("security_privacy", "Security & Data Privacy", True),
    ("functionality", "Functionality & Features", True),
    ("ease_of_use", "Ease of Use", False),
    ("pricing_value", "Pricing & Value", True),
    ("reliability", "Reliability & Performance", False),
    ("integrations", "Integration Capabilities", True),
    ("support", "Customer Support", True),
    ("company_stability", "Company Stability", True),
    ("update_frequency", "Update Frequency", True),
    ("startup_friendliness", "Startup-Friendliness", True),
)

AUTOMATABLE = tuple(cid for cid, _n, auto in CRITERIA if auto)
MANUAL_ONLY = tuple(cid for cid, _n, auto in CRITERIA if not auto)
CRITERION_NAMES = {cid: name for cid, name, _a in CRITERIA}

# Matches the model field: overall_score stays null below this.
MIN_CRITERIA_FOR_SCORE = 6
MAX_CRITERION_SCORE = 10
# Security is stored separately on a 0-20 scale.
SECURITY_SCALE = 20
# A missing privacy/security page can support a low published-posture
# score. A 404 on /changelog or /integrations is not a product rating —
# it is "we did not find a page" and must stay unassessed.
ABSENT_SCORE_CAP = 4
ABSENCE_SCORES_ONLY = frozenset({"security_privacy"})

# Dedicated-path hints. Homepage (and GitHub) may still support several
# criteria when the visible text actually contains the facts.
CRITERION_PATH_HINTS = {
    "security_privacy": (
        "privacy",
        "security",
        "trust",
        "legal",
        "dpa",
        "gdpr",
        "terms",
        "policy",
    ),
    "functionality": ("feature", "product", "platform", "solution"),
    "pricing_value": ("pricing", "plans", "billing", "subscribe"),
    "integrations": (
        "integrat",
        "apps",
        "marketplace",
        "plugin",
        "connect",
        "partners",
    ),
    "support": ("support", "contact", "help", "docs", "doc", "faq", "community"),
    "company_stability": (
        "about",
        "team",
        "company",
        "investors",
        "press",
        "careers",
    ),
    "update_frequency": ("changelog", "releases", "whats-new", "news", "blog"),
    "startup_friendliness": (
        "startup",
        "pricing",
        "plans",
        "students",
        "education",
        "free",
    ),
}
HOMEPAGE_OK = frozenset(AUTOMATABLE)

# Where evidence for each automatable criterion usually lives. Used to
# steer the fetcher, and shown to the model so it knows what to look for.
EVIDENCE_HINTS = {
    "security_privacy": (
        "HTTPS scheme, /privacy or /privacy-policy, /security, /trust, "
        "stated SOC 2 / GDPR / DPA / retention. Not a test of controls."
    ),
    "functionality": "the product or features page, or the homepage",
    "pricing_value": "/pricing, /plans, or plans/free tier stated on the homepage",
    "integrations": (
        "/integrations, /apps, marketplace, or named connectors on the homepage"
    ),
    "support": "/support, /contact, /docs — never a blog post",
    "company_stability": "about/team page, funding mention, GitHub archive flag",
    "update_frequency": "/changelog, /releases, recent commit dates",
    "startup_friendliness": "free tier, startup programme, credits page",
}

SYSTEM_PROMPT = """You score software tools for a public directory. \
Visitors will see these numbers next to the product. They must look like \
a careful reading of published pages, not a penalty for missing URLs.

You will be given evidence gathered from a tool's own site or GitHub. \
Score ONLY the criteria you were asked about.

Hard rules:
- Score a criterion ONLY when a PRESENT page (present=true) actually \
discusses it. If it does not, return null. Null is correct. Guessing \
is a failure.
- Do NOT score 0 because /pricing, /integrations, /changelog, or \
/support 404'd. That is missing evidence, not a bad product. Return \
null unless another PRESENT page (often the homepage) covers that \
criterion.
- The homepage MAY support functionality, pricing (plans/free tier \
visible), support (contact/docs/help visible), company stability \
(team/about/founded), startup-friendliness (free tier/credits), and \
integrations (named connectors). Cite the homepage only when its text \
contains those facts.
- Typical present-page scores are 6-8. Use 5 for a thin but real page. \
Reserve 9-10 for unusually complete published info (e.g. privacy + \
named SOC 2/GDPR/DPA). Use 0-3 only when a PRESENT page shows a real \
problem (no HTTPS, policy says data is sold with no controls).
- Every score MUST cite an evidence_url from the evidence provided.
- Never infer a score from popularity or your training knowledge. \
Grade the evidence, not the brand.
- Security is published posture only: HTTPS in transit, a reachable \
privacy policy, stated SOC 2 / GDPR / DPA / retention. You did not \
test controls. Never say verified, audited, or penetration tested.
- The one 404 exception: a missing privacy/security page MAY score \
0-4 for Security & Data Privacy, citing that URL, if HTTPS is the \
only other signal. A 403 or failed fetch is not absence — return null.
- Customer Support must cite /support, /contact, /help, /docs, or a \
homepage that actually shows those. Never cite a blog or article.
- Do not score Ease of Use or Reliability.

Return a single JSON object, no prose."""


def _client() -> OpenAI:
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _model_name() -> str:
    return getattr(settings, "HYGIENE_ASSESS_MODEL", DEFAULT_MODEL)


def token_cost_usd(
    prompt_tokens: int, completion_tokens: int, model: str = DEFAULT_MODEL
) -> float:
    rates = USD_PER_MILLION.get(model, UNKNOWN_MODEL_RATES)
    return (prompt_tokens * rates[0] + completion_tokens * rates[1]) / 1_000_000


def empty_usage() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}


def _usage_from(response, model: str) -> dict:
    usage = getattr(response, "usage", None)
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cost_usd": round(token_cost_usd(prompt, completion, model), 6),
    }


def build_prompt_payload(name: str, website: str, evidence: dict) -> dict:
    """Everything the model may reason from, plus the shape to return."""
    return {
        "tool_name": name,
        "website": website,
        "evidence": evidence,
        "score_these_criteria": {
            cid: {"name": CRITERION_NAMES[cid], "look_for": EVIDENCE_HINTS.get(cid, "")}
            for cid in AUTOMATABLE
        },
        "response_shape": {
            cid: {
                "score": "integer 0-10, or null if unsupported",
                "evidence_url": "url from the evidence, or null",
                "reasoning": "one short sentence citing what the evidence showed",
            }
            for cid in AUTOMATABLE
        },
    }


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _is_homepage_url(url: str) -> bool:
    path = (urlparse(url).path or "/").rstrip("/") or "/"
    return path == "/"


def _host(url: str) -> str:
    return (urlparse(url).netloc or "").lower().removeprefix("www.")


def citation_fits(criterion_id: str, url: str, cited: dict) -> bool:
    """Drop citations that cannot reasonably support the criterion.

    A 404 may only score Security & Data Privacy. Support cannot cite a
    blog post. Homepage is allowed when the page is actually present.
    """
    if not cited.get("present"):
        return bool(cited.get("absence") and criterion_id in ABSENCE_SCORES_ONLY)
    host = _host(url)
    if host.endswith("github.com") or host == "raw.githubusercontent.com":
        return True
    path = (urlparse(url).path or "/").lower()
    hints = CRITERION_PATH_HINTS.get(criterion_id, ())
    if any(hint in path for hint in hints):
        return True
    if criterion_id in HOMEPAGE_OK and _is_homepage_url(url):
        return True
    if criterion_id == "security_privacy":
        return True
    return False


def _evidence_index(evidence: dict) -> dict[str, dict]:
    index = {}
    for item in evidence.values():
        if not isinstance(item, dict):
            continue
        url = _normalize_url(item.get("url") or "")
        if url:
            index[url] = item
            index[url.replace("http://", "https://")] = item
    return index


def _valid_entry(raw, evidence_index: dict, criterion_id: str = "") -> dict | None:
    """A criterion counts only if it has both a score and a citation."""
    if not isinstance(raw, dict):
        return None
    score = raw.get("score")
    url = (raw.get("evidence_url") or "").strip()
    if score is None or not url:
        return None
    try:
        value = int(score)
    except (TypeError, ValueError):
        return None
    if not 0 <= value <= MAX_CRITERION_SCORE:
        return None
    cited = evidence_index.get(_normalize_url(url))
    if cited is None:
        cited = evidence_index.get(_normalize_url(url).replace("http://", "https://"))
    if cited is None:
        return None
    if not citation_fits(criterion_id, url, cited):
        return None
    if not cited.get("present"):
        if value > ABSENT_SCORE_CAP:
            return None
        url = cited.get("url") or url
    else:
        url = cited.get("url") or url
    return {
        "score": value,
        "evidence_url": url,
        "reasoning": str(raw.get("reasoning") or "").strip(),
    }


def overall_from(scored: dict) -> float | None:
    """Unweighted mean of scored criteria on a 0-5 scale, or None below the gate."""
    if len(scored) < MIN_CRITERIA_FOR_SCORE:
        return None
    mean = sum(entry["score"] for entry in scored.values()) / len(scored)
    return round(mean / 2.0, 2)


def security_score_from(scored: dict) -> int | None:
    """Security is stored 0-20; the rubric scores it 0-10."""
    entry = scored.get("security_privacy")
    if entry is None:
        return None
    return int(round(entry["score"] * (SECURITY_SCALE / MAX_CRITERION_SCORE)))


def assessment_detail(result: dict, *, model: str, hands_on: bool = False) -> dict:
    """Full 10-criterion record for the rating page, including nulls."""
    scored = result.get("scored") or {}
    criteria = {}
    for cid, name, automated in CRITERIA:
        if cid in scored:
            criteria[cid] = {**scored[cid], "name": name, "automated": automated}
        else:
            reason = (
                "Requires hands-on use of the product."
                if not automated
                else "No citable published evidence in this pass."
            )
            criteria[cid] = {
                "name": name,
                "score": None,
                "evidence_url": None,
                "reasoning": reason,
                "automated": automated,
            }
    return {
        "version": 1,
        "method": "published_evidence",
        "hands_on": hands_on,
        "model": model,
        "criteria": criteria,
        "unassessed": result.get("unassessed") or [],
        "manual_only": list(MANUAL_ONLY),
    }


def _empty_result(**extra) -> dict:
    payload = {
        "scored": {},
        "unassessed": list(AUTOMATABLE),
        "manual_only": list(MANUAL_ONLY),
        "criteria_completed": 0,
        "overall_score": None,
        "security_criterion_score": None,
        "usage": empty_usage(),
    }
    payload.update(extra)
    return payload


def assess(name: str, website: str, evidence: dict) -> dict:
    """Score one tool. Returns criteria, counts, derived scores, and usage."""
    if not evidence:
        return _empty_result()

    model = _model_name()
    payload = build_prompt_payload(name, website, evidence)
    try:
        response = _client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, default=str)},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1200,
        )
        data = json.loads(response.choices[0].message.content or "{}")
        usage = _usage_from(response, model)
    except (OpenAIError, json.JSONDecodeError, IndexError, TypeError) as exc:
        logger.warning("Assessment failed for %s: %s", name, exc)
        return _empty_result(error=str(exc))

    evidence_index = _evidence_index(evidence)
    scored: dict[str, dict] = {}
    for cid in AUTOMATABLE:
        entry = _valid_entry(data.get(cid), evidence_index, cid)
        if entry is not None:
            scored[cid] = entry

    return {
        "scored": scored,
        "unassessed": [cid for cid in AUTOMATABLE if cid not in scored],
        "manual_only": list(MANUAL_ONLY),
        "criteria_completed": len(scored),
        "overall_score": overall_from(scored),
        "security_criterion_score": security_score_from(scored),
        "usage": usage,
    }
