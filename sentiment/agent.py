import anthropic
import json
import logging
from django.conf import settings
from django.utils import timezone
from .models import ToolSentiment
from .scraper import gather_all_mentions

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

AGENT_SYSTEM_PROMPT = """
You are a senior analyst at One9Founders, India's security-validated AI tools 
directory. Your job is to analyse raw online mentions of AI tools and extract 
structured, honest sentiment data that helps founders make better decisions.

You think like an experienced founder. you care about:
- Real workflow impact, not hype
- Pricing fairness and transparency
- Data privacy and security
- Whether the tool actually works as advertised

You are sceptical of overly positive reviews and alert to red flags.
"""

ANALYSIS_PROMPT = """
Analyse these online mentions of the AI tool: "{tool_name}"

MENTIONS:
{mentions_text}

Return ONLY a valid JSON object. No explanation, no markdown, just the JSON.

{{
  "overall_score": <float between 0.0 and 1.0>,
  "sentiment_label": "<positive|mixed|negative|insufficient_data>",
  "positive_count": <integer>,
  "negative_count": <integer>,
  "neutral_count": <integer>,
  "top_praises": [<max 3 short phrases, each under 6 words>],
  "top_complaints": [<max 3 short phrases, each under 6 words>],
  "red_flags": [<only serious issues: data breaches, scams, sudden shutdowns, 
                hidden charges. Empty list if none>],
  "one_line_summary": "<one sentence, max 20 words, what founders think overall>"
}}
"""

def run_sentiment_agent(tool_name: str) -> ToolSentiment:
    logger.info(f"[Agent] Starting sentiment analysis for: {tool_name}")

    # Step 1. Gather raw mentions
    mentions = gather_all_mentions(tool_name)

    # Step 2. Handle no data case
    if len(mentions) < 2:
        logger.info(f"[Agent] Insufficient data for {tool_name}")
        sentiment, _ = ToolSentiment.objects.get_or_create(tool_name=tool_name)
        sentiment.sentiment_label = 'insufficient_data'
        sentiment.confidence = 'none'
        sentiment.source_count = len(mentions)
        sentiment.last_analysed = timezone.now()
        sentiment.save()
        return sentiment

    # Step 3. Format mentions for Claude
    mentions_text = ""
    for i, mention in enumerate(mentions[:15], 1):
        mentions_text += f"\n[{i}] Source: {mention['source']}\n{mention['text']}\n"

    # Step 4. Send to Claude
    logger.info(f"[Agent] Sending {len(mentions)} mentions to Claude...")
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=AGENT_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": ANALYSIS_PROMPT.format(
                    tool_name=tool_name,
                    mentions_text=mentions_text
                )
            }]
        )
        raw_output = response.content[0].text.strip()
        logger.info(f"[Agent] Claude responded for {tool_name}")
    except Exception as e:
        logger.error(f"[Agent] Claude API error for {tool_name}: {e}")
        raise

    # Step 5. Pass to quality gate
    from .quality_gate import run_quality_gate
    validated_result = run_quality_gate(raw_output, len(mentions), tool_name)

    # Step 6. Save to database
    sentiment, created = ToolSentiment.objects.get_or_create(tool_name=tool_name)
    sentiment.overall_score = validated_result.get('overall_score', 0.5)
    sentiment.sentiment_label = validated_result.get('sentiment_label', 'insufficient_data')
    sentiment.confidence = validated_result.get('confidence', 'none')
    sentiment.source_count = len(mentions)
    sentiment.top_praises = validated_result.get('top_praises', [])
    sentiment.top_complaints = validated_result.get('top_complaints', [])
    sentiment.red_flags = validated_result.get('red_flags', [])
    sentiment.one_line_summary = validated_result.get('one_line_summary', '')
    sentiment.was_corrected = validated_result.get('was_corrected', False)
    sentiment.last_analysed = timezone.now()
    sentiment.save()

    action = "Created" if created else "Updated"
    logger.info(f"[Agent] {action} sentiment for {tool_name}: {sentiment.sentiment_label} ({sentiment.overall_score})")

    # Step 7. Alert if red flags found
    if sentiment.red_flags:
        notify_red_flag(tool_name, sentiment.red_flags)

    return sentiment


def notify_red_flag(tool_name, red_flags):
    logger.critical(f"RED FLAG DETECTED: {tool_name} | Issues: {red_flags}")
    # Slack webhook will be added here in next step