import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Build FAISS index from all active tools for fast similarity search"

    def handle(self, *args, **options):
        from api.faiss_search import FAISSSearchService

        self.stdout.write("Building FAISS index...")
        start_time = time.time()

        service = FAISSSearchService.get_instance()
        count = service.build_index()

        elapsed = time.time() - start_time

        if count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"FAISS index built: {count} tools indexed in {elapsed:.2f}s"
                )
            )
        else:
            self.stdout.write(self.style.WARNING("No tools found to index"))
