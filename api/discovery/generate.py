"""Generate an original tool description from structured facts only."""

import logging

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
