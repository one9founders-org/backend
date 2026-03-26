import logging

import requests
from django.core.management.base import BaseCommand
from django.db import transaction

from research_papers.models import Paper

logger = logging.getLogger(__name__)

HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"


class Command(BaseCommand):
    help = "Sync trending papers from HuggingFace daily papers"

    def handle(self, *args, **options):
        self.stdout.write("Fetching HuggingFace daily papers...")

        try:
            resp = requests.get(HF_DAILY_PAPERS_URL, timeout=30)
            resp.raise_for_status()
            papers_data = resp.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch HF papers: {e}"))
            return

        updated = 0
        not_found = 0

        with transaction.atomic():
            # Reset trending flags inside transaction for atomicity
            reset_count = Paper.objects.filter(is_trending=True).update(
                is_trending=False
            )
            self.stdout.write(f"Reset {reset_count} previously trending papers")

            for item in papers_data:
                try:
                    paper_info = item.get("paper", item)
                    arxiv_id = paper_info.get("id", "")
                    if not arxiv_id:
                        continue

                    try:
                        paper = Paper.objects.get(arxiv_id=arxiv_id)
                    except Paper.DoesNotExist:
                        not_found += 1
                        continue

                    upvotes = item.get("numUpvotes", paper_info.get("upvotes", 0))
                    hf_url = f"https://huggingface.co/papers/{arxiv_id}"

                    paper.hf_upvotes = upvotes
                    paper.hf_url = hf_url
                    paper.is_trending = True

                    # Check for code repos
                    media_urls = item.get("mediaUrls", [])
                    for url in media_urls:
                        if "github.com" in url and not paper.code_url:
                            paper.code_url = url

                    paper.save(
                        update_fields=[
                            "hf_upvotes",
                            "hf_url",
                            "is_trending",
                            "code_url",
                        ]
                    )
                    updated += 1

                except Exception as e:
                    logger.warning("Error processing HF paper: %s", e)
                    continue

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} trending papers, {not_found} not in database"
            )
        )
