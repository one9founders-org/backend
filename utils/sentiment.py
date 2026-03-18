import os
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Literal

# Initialize the OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 1. Define the Expected Output Structure
class AspectEvaluation(BaseModel):
    aspect: Literal["Pricing", "Speed", "Accuracy", "UX", "Support", "API", "Other"]
    sentiment: Literal["Positive", "Negative", "Mixed", "Neutral"]
    explanation: str = Field(description="A brief 1-sentence reason for this sentiment based on the text.")

class ReviewAnalysis(BaseModel):
    tool_name: str
    aspects: List[AspectEvaluation]

# 2. The Core ABSA Function
def analyze_review_sentiment(review_text: str) -> ReviewAnalysis:
    prompt = f"""
    You are an expert software reviewer. Analyze the following review.
    Extract the tool being discussed and evaluate the sentiment for these specific aspects ONLY: 
    Pricing, Speed, Accuracy, UX, Support, API.
    
    If an aspect is not mentioned in the review, do not include it.
    
    Review Text:
    "{review_text}"
    """

    response = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06", # OpenAI's best model for exact structured data
        messages=[
            {"role": "system", "content": "You are a helpful data extraction assistant."},
            {"role": "user", "content": prompt}
        ],
        response_format=ReviewAnalysis,
    )

    return response.choices[0].message.parsed


# --- The Aggregation Logic (Stays exactly the same) ---

SENTIMENT_SCORES = {
    "Positive": 1.0,
    "Mixed": 0.5,
    "Neutral": 0.0,
    "Negative": -1.0
}

ASPECT_WEIGHTS = {
    "Accuracy": 1.5,
    "API": 1.2,
    "Speed": 1.0,
    "Pricing": 1.0,
    "Support": 0.8,
    "UX": 0.8,
    "Other": 0.5
}

def calculate_weighted_score(analysis: ReviewAnalysis) -> float:
    total_score = 0
    total_weight = 0
    
    for item in analysis.aspects:
        score = SENTIMENT_SCORES.get(item.sentiment, 0)
        weight = ASPECT_WEIGHTS.get(item.aspect, 1.0)
        
        total_score += (score * weight)
        total_weight += weight
        
    if total_weight == 0:
        return 0.0
        
    return total_score / total_weight