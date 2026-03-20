import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.pipeline_engine import PipelineOrchestrator, ingest_scraper_output
from scrapers.rss_news.scraper import RSSNewsScraper

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Runs the full news automation pipeline: Scrape -> Score -> Generate -> Publish'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Max items to scrape per source'
        )
        parser.add_argument(
            '--publish-limit',
            type=int,
            default=5,
            help='Max items to publish in this run'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force run even if daily limit might be reached'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        publish_limit = options['publish_limit']
        
        self.stdout.write(self.style.SUCCESS(f"[{timezone.now()}] Starting News Automation Pipeline"))
        
        try:
            # 1. Scrape
            self.stdout.write("Phase 1: Scraping RSS Feeds...")
            scraper = RSSNewsScraper(limit_per_source=limit)
            items = scraper.scrape()
            
            # 2. Ingest
            self.stdout.write(f"Phase 2: Ingesting {len(items)} items...")
            added, skipped = ingest_scraper_output("rss_news", items)
            self.stdout.write(self.style.SUCCESS(f"Ingested {added} items, skipped {skipped} duplicates"))
            
            # 3. Run Pipeline (Score -> Generate -> Publish)
            self.stdout.write("Phase 3: Running Pipeline Orchestrator...")
            orchestrator = PipelineOrchestrator()
            run = orchestrator.run_full_pipeline(
                source="rss_news",
                score_limit=added + 5, # Process at least the new ones
                generate_limit=limit,
                publish_limit=publish_limit
            )
            
            if run.status == "completed":
                self.stdout.write(self.style.SUCCESS(
                    f"Pipeline Run Completed: {run.items_succeeded} succeeded, {run.items_failed} failed"
                ))
            else:
                self.stdout.write(self.style.ERROR(f"Pipeline Run Failed: {run.error_message}"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Critical error in news pipeline: {str(e)}"))
            logger.error(f"News pipeline error: {e}", exc_info=True)

        self.stdout.write(self.style.SUCCESS(f"[{timezone.now()}] News Automation Pipeline Finished"))
