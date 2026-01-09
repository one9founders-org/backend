import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import google.generativeai as genai
from django.conf import settings

from api.models import Tool

genai.configure(api_key=settings.GEMINI_API_KEY)


def generate_embedding(tool_data):
    tool_id, text = tool_data
    try:
        result = genai.embed_content(model="models/text-embedding-004", content=text)
        return tool_id, result["embedding"], None
    except Exception as e:
        return tool_id, None, str(e)


tools = Tool.objects.filter(embedding__isnull=True)
print(f"Generating embeddings for {tools.count()} tools...")

tool_data = [(tool.id, f"{tool.name} - {tool.description}") for tool in tools]
updates = []

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(generate_embedding, data): data for data in tool_data}

    for future in as_completed(futures):
        tool_id, embedding, error = future.result()
        if embedding:
            updates.append(Tool(id=tool_id, embedding=embedding))
            print(f"✓ Tool {tool_id}")
        else:
            print(f"✗ Tool {tool_id}: {error}")

if updates:
    Tool.objects.bulk_update(updates, ["embedding"])
    print(f"Updated {len(updates)} tools in bulk")

print("Done!")
