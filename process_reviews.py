import json
import os

import django

# 1. Setup Django environment so we can use the database
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from api.models import Tool, ToolSentimentLog
from utils.sentiment import analyze_review_sentiment, calculate_weighted_score

# I am including a mock review here so you can test it immediately.
# Later, you will swap this to read from your scrapers/ folder.
MOCK_SCRAPED_DATA = [
    {
        "source": "G2",
        "review_text": "I've been using Notion for a week. The API is incredibly fast and the data accuracy is spot on. However, their pricing is way too expensive for startups, and the user dashboard is clunky. Support hasn't replied to my email in 3 days.",
    }
]


def run_pipeline():
    print("Starting Sentiment Analysis Pipeline...\n")

    # In the future, uncomment these lines to load actual scraper data:
    # with open('scrapers/g2_reviews.json', 'r') as file:
    #     reviews = json.load(file)
    reviews = MOCK_SCRAPED_DATA

    for item in reviews:
        text = item.get("review_text")
        source = item.get("source", "Unknown")

        if not text:
            continue

        print(f"Analyzing review from {source}...")

        # Step A: Run the AI ABSA Engine
        analysis = analyze_review_sentiment(text)
        score = calculate_weighted_score(analysis)

        print(f"-> Detected Tool: {analysis.tool_name}")
        print(f"-> Calculated Score: {score:.2f}")

        # Step B: Find or Create the Tool in the Database
        # (This prevents crashes since your local DB is currently empty!)
        db_tool, created = Tool.objects.get_or_create(
            name=analysis.tool_name,
            defaults={
                "description": f"Auto-generated entry for {analysis.tool_name}",
                "short_description": "Added via sentiment pipeline",
                "slug": analysis.tool_name.lower().replace(" ", "-"),
            },
        )

        if created:
            print(f"-> [*] Created new missing Tool in database: '{db_tool.name}'")

        # Step C: Save the Sentiment Log (The Memory Layer)
        log = ToolSentimentLog.objects.create(
            tool=db_tool,
            source=source,
            weighted_score=score,
            # Convert Pydantic objects to dicts so Django can save them as JSON
            raw_aspect_data=[aspect.model_dump() for aspect in analysis.aspects],
        )

        print(f"-> [+] Success! Saved sentiment log to database! (Log ID: {log.id})\n")


if __name__ == "__main__":
    run_pipeline()
