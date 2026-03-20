import json
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

DAILY_PROCESSING_CAP = 200


def _get_openai_client():
    """Return an OpenAI client using the configured API key."""
    from openai import OpenAI

    return OpenAI(api_key=settings.OPENAI_API_KEY)


def _is_valid_domain(domain: str) -> bool:
    """
    Basic domain validation: must have a TLD, not be an IP address,
    and not contain obvious spam patterns.
    """
    if not domain:
        return False

    # Reject IP addresses
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", domain):
        return False

    # Must have at least one dot (TLD)
    if "." not in domain:
        return False

    # TLD must be at least 2 characters
    tld = domain.rsplit(".", 1)[-1]
    if len(tld) < 2:
        return False

    # Basic character validation
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-\.]*[a-zA-Z0-9]$", domain):
        return False

    return True


def verify_ai_tool(domain: str) -> dict:
    """
    Ask OpenAI if this domain is an AI tool.
    Returns: {"is_ai_tool": bool, "reason": str}
    """
    client = _get_openai_client()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a classifier that determines if a website/domain "
                    "is an AI tool or AI-powered product.\n\n"
                    'An "AI tool" means: a product, platform, or service that '
                    "uses artificial intelligence, machine learning, large "
                    "language models, generative AI, computer vision, NLP, or "
                    "similar AI/ML technology as a core feature.\n\n"
                    "Examples of AI tools: chatgpt.com, midjourney.com, "
                    "runway.ml, jasper.ai, notion.so (has AI features), "
                    "canva.com (has AI features)\n"
                    "Examples of NOT AI tools: amazon.com (e-commerce), "
                    "wikipedia.org (encyclopedia), stackoverflow.com (forum), "
                    "github.com (code hosting, not primarily AI)\n\n"
                    "Respond ONLY with valid JSON, no markdown, no backticks:\n"
                    '{"is_ai_tool": true/false, "reason": "brief explanation"}'
                ),
            },
            {
                "role": "user",
                "content": f"Is this domain an AI tool? Domain: {domain}",
            },
        ],
        temperature=0,
        max_tokens=150,
    )

    text = response.choices[0].message.content.strip()
    return json.loads(text)


def generate_tool_data(domain: str) -> dict:
    """
    Ask OpenAI to generate structured tool data for an AI tool.
    Returns: {
        "name": str, "description": str, "category": str,
        "pricing": str, "features": list
    }
    """
    client = _get_openai_client()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a data generator for an AI tools directory. "
                    "Given a domain, generate accurate structured data about "
                    "the AI tool.\n\n"
                    "Use these exact categories (pick the best fit):\n"
                    "Text, Images, Video, Audio, Code, Chatbots, Productivity, "
                    "Marketing, Design, Data Analysis, Education, Healthcare, "
                    "Finance, Legal, HR, Customer Support, Sales, SEO, "
                    "Social Media, Writing, Translation, Research, Automation, "
                    "3D, Gaming, Music, Presentation, Spreadsheets, Email, "
                    "Meeting, Other\n\n"
                    "For pricing, use one of: Free, Freemium, Paid, "
                    "Free Trial, Contact for Pricing, Open Source\n\n"
                    "Respond ONLY with valid JSON, no markdown, no backticks:\n"
                    "{\n"
                    '  "name": "Tool Name",\n'
                    '  "description": "1-2 sentence description of what the '
                    'tool does. Be specific and factual.",\n'
                    '  "category": "Category from the list above",\n'
                    '  "pricing": "Pricing model from the list above",\n'
                    '  "features": ["feature 1", "feature 2", "feature 3"]\n'
                    "}"
                ),
            },
            {
                "role": "user",
                "content": (f"Generate tool data for this AI tool domain: {domain}"),
            },
        ],
        temperature=0.1,
        max_tokens=300,
    )

    text = response.choices[0].message.content.strip()
    return json.loads(text)


# Map OpenAI pricing labels to Tool.pricing_type choices
PRICING_MAP = {
    "free": "free",
    "freemium": "freemium",
    "paid": "paid",
    "free trial": "paid",
    "contact for pricing": "paid",
    "open source": "free",
}


def process_tool_suggestion(suggestion):
    """
    Process a single ToolSuggestion:
    1. Verify if it's an AI tool
    2. If yes, generate data and create a draft Tool
    3. Update the suggestion with results
    """
    from api.models import Tool, ToolSuggestion

    domain = suggestion.domain

    # Daily processing cap
    today_count = ToolSuggestion.objects.filter(
        processed_at__gte=timezone.now() - timedelta(days=1),
        processed_at__isnull=False,
    ).count()

    if today_count >= DAILY_PROCESSING_CAP:
        logger.info(
            "Daily processing cap (%d) reached, skipping.", DAILY_PROCESSING_CAP
        )
        return

    # Validate domain format
    if not _is_valid_domain(domain):
        suggestion.ai_reason = "Invalid domain format"
        suggestion.status = "rejected"
        suggestion.processed_at = timezone.now()
        suggestion.save()
        return

    # Check if domain already exists in Tool table
    if Tool.objects.filter(domain=domain).exists():
        suggestion.status = "rejected"
        suggestion.ai_reason = "Tool with this domain already exists in directory"
        suggestion.processed_at = timezone.now()
        suggestion.save()
        return

    # Verify with OpenAI
    try:
        verification = verify_ai_tool(domain)
    except Exception as e:
        suggestion.ai_reason = f"OpenAI verification failed: {str(e)}"
        suggestion.processed_at = timezone.now()
        suggestion.save()
        logger.warning("OpenAI verification failed for %s: %s", domain, e)
        return

    suggestion.is_ai_tool = verification.get("is_ai_tool", False)
    suggestion.ai_reason = verification.get("reason", "")

    if not suggestion.is_ai_tool:
        suggestion.status = "rejected"
        suggestion.processed_at = timezone.now()
        suggestion.save()
        return

    # Generate tool data
    try:
        tool_data = generate_tool_data(domain)
    except Exception as e:
        suggestion.ai_reason += f" | Data generation failed: {str(e)}"
        suggestion.processed_at = timezone.now()
        suggestion.save()
        logger.warning("Tool data generation failed for %s: %s", domain, e)
        return

    suggestion.generated_data = tool_data

    # Create draft Tool (is_active=False so it's not publicly visible)
    try:
        from django.utils.text import slugify

        name = tool_data.get("name", domain)
        slug = slugify(name)

        # Ensure unique slug
        base_slug = slug
        counter = 1
        while Tool.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Ensure unique name
        original_name = name
        name_counter = 1
        while Tool.objects.filter(name=name).exists():
            name = f"{original_name} ({name_counter})"
            name_counter += 1

        # Map pricing string to pricing_type choice
        pricing_label = tool_data.get("pricing", "Freemium").lower()
        pricing_type = PRICING_MAP.get(pricing_label, "freemium")

        tool = Tool.objects.create(
            name=name,
            slug=slug,
            description=tool_data.get("description", ""),
            website=f"https://{domain}",
            domain=domain,
            pricing_type=pricing_type,
            features=tool_data.get("features", []),
            is_active=False,  # Draft — not publicly visible until approved
        )

        suggestion.auto_created_tool = tool
        suggestion.status = "reviewed"
    except Exception as e:
        suggestion.ai_reason += f" | Tool creation failed: {str(e)}"
        logger.warning("Draft tool creation failed for %s: %s", domain, e)

    suggestion.processed_at = timezone.now()
    suggestion.save()
