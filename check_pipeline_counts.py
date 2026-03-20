import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.pipeline_models import ScrapedItem, QualifiedNewsItem, NewsDraft, PublishedArticle
from api.models import News

print("--- Pipeline Model Counts ---")
print(f"Scraped Items: {ScrapedItem.objects.count()}")
print(f"Qualified News Items: {QualifiedNewsItem.objects.count()}")
print(f"News Drafts: {NewsDraft.objects.count()}")
print(f"Published Articles (Pipeline): {PublishedArticle.objects.count()}")
print(f"Total News Articles: {News.objects.count()}")
