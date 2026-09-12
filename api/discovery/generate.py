"""Generate an original tool description from structured facts only."""

import logging
import re

from django.conf import settings
from openai import OpenAI

from . import TARGET_DESCRIPTION_WORDS
from .facts import Facts

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You write factual directory blurbs for software tools.
Rules:
- Write an original 40 to 80 word description in your own words.
- Do not use phrases directly from any source material.
- Do not write marketing copy, superlatives, or slogans.
- Describe what the tool does and who it is for, factually.
- Do not mention that you are an AI.
Return only the description text."""

FORGE_SOURCES = frozenset({"github", "gitlab", "codeberg"})


def oss_attribution_description(
    tool_name: str,
    facts: Facts,
    *,
    source_url: str = "",
    source_type: str = "github",
) -> str:
    """Deterministic blurb that credits the forge + maintainers (no LLM)."""
    platform = {
        "github": "GitHub",
        "gitlab": "GitLab",
        "codeberg": "Codeberg",
    }.get((source_type or "").lower(), "GitHub")
    bare = (tool_name or "").strip()
    if bare.lower().startswith(("github/", "gitlab/", "codeberg/")):
        bare = bare.split("/", 1)[-1]
    owner = bare.split("/")[0] if "/" in bare else bare
    repo = bare.split("/")[-1] if "/" in bare else bare
    about = (facts.meta_description or facts.source_text or "").strip()
    about = re.sub(r"\s+", " ", about)
    if len(about) > 220:
        about = about[:217].rstrip() + "…"
    stars = facts.stars
    star_bit = f" It has {stars:,} stars on {platform}." if stars else ""
    license_bit = ""
    # license may live on topics/category side-channels; keep optional.
    if facts.category:
        license_bit = f" Commonly categorised as {facts.category}."
    if about:
        body = (
            f"{repo} is an open-source project by {owner} on {platform}. "
            f"{about}{star_bit}{license_bit} "
            f"All credit belongs to the maintainers; "
            f"One9Founders lists it for discovery with a link to the source."
        )
    else:
        body = (
            f"{repo} is an open-source repository by {owner} hosted on {platform}."
            f"{star_bit}{license_bit} "
            f"One9Founders indexes public OSS AI tools and credits the original "
            f"developers via the upstream project page"
            f"{f' at {source_url}' if source_url else ''}."
        )
    return re.sub(r"\s+", " ", body).strip()


def _facts_for_prompt(facts: Facts) -> dict:
    return {
        "title": facts.title,
        "pricing": facts.pricing,
        "category": facts.category,
        "topics": facts.topics,
        "stars": facts.stars,
    }


def generate_description(
    tool_name: str,
    facts: Facts,
    extra_instruction: str = "",
) -> str:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    low, high = TARGET_DESCRIPTION_WORDS
    user_parts = [
        f"Tool name: {tool_name}",
        "Structured facts (do not copy wording from anywhere else): "
        f"{_facts_for_prompt(facts)}",
        f"Write {low}-{high} words.",
    ]
    if extra_instruction:
        user_parts.append(extra_instruction)

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_parts)},
        ],
        temperature=0.7,
        max_tokens=220,
    )
    text = (response.choices[0].message.content or "").strip()
    return text.strip().strip('"')
