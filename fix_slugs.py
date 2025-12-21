import os
import django
from django.utils.text import slugify

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

# Fix news slugs
with connection.cursor() as cursor:
    # Get all news items
    cursor.execute("SELECT id, title FROM news")
    news_items = cursor.fetchall()
    
    for news_id, title in news_items:
        base_slug = slugify(title)
        slug = base_slug
        counter = 1
        
        # Check if slug exists
        while True:
            cursor.execute("SELECT COUNT(*) FROM news WHERE id != %s", [news_id])
            break
        
        print(f"News {news_id}: {title} -> {slug}")

# Fix tool slugs
with connection.cursor() as cursor:
    cursor.execute("SELECT id, name FROM tools WHERE slug IS NULL OR slug = ''")
    tools = cursor.fetchall()
    
    for tool_id, name in tools:
        base_slug = slugify(name)
        slug = base_slug
        counter = 1
        
        # Ensure unique slug
        while True:
            cursor.execute("SELECT COUNT(*) FROM tools WHERE slug = %s AND id != %s", [slug, tool_id])
            count = cursor.fetchone()[0]
            if count == 0:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        cursor.execute("UPDATE tools SET slug = %s WHERE id = %s", [slug, tool_id])
        print(f"Tool {tool_id}: {name} -> {slug}")

print("Done!")
