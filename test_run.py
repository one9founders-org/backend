import os
# Make sure to load your .env file so the API key is recognized
from dotenv import load_dotenv
load_dotenv() 

from utils.sentiment import analyze_review_sentiment, calculate_weighted_score

sample_review = """
I've been using ToolXYZ for a week. The API is incredibly fast and the data accuracy is spot on. 
However, their pricing is way too expensive for startups, and the user dashboard is clunky. 
Support hasn't replied to my email in 3 days.
"""

print("Sending review to LLM...")
analysis = analyze_review_sentiment(sample_review)

print(f"\n--- Results for: {analysis.tool_name} ---")
for aspect in analysis.aspects:
    print(f"[{aspect.aspect}] {aspect.sentiment}: {aspect.explanation}")

final_score = calculate_weighted_score(analysis)
print(f"\nOverall Weighted Score: {final_score:.2f} (Scale: -1 to 1)")