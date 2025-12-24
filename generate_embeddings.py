import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import google.generativeai as genai
from django.conf import settings

from api.models import Tool

genai.configure(api_key=settings.GEMINI_API_KEY)

tools = Tool.objects.filter(embedding__isnull=True)
print(f"Generating embeddings for {tools.count()} tools...")

for tool in tools:
    text = f"{tool.name} - {tool.description}"
    try:
        result = genai.embed_content(model="models/text-embedding-004", content=text)
        tool.embedding = result["embedding"]
        tool.save()
        print(f"✓ {tool.name}")
    except Exception as e:
        print(f"✗ {tool.name}: {e}")

print("Done!")
