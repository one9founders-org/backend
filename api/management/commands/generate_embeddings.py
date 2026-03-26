"""
generate_embeddings management command — fixed version.

Fixes vs original:
  - Uses openai>=1.0.0 client API (OpenAI() instance, not module-level calls).
  - Accesses response as object attributes, not dict keys.
  - Adds --force flag to re-generate embeddings for all tools (not just missing ones).
  - Better progress reporting and error logging.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.core.management.base import BaseCommand
from openai import OpenAI

from api.models import Tool


class Command(BaseCommand):
    help = "Generate OpenAI embeddings for tools (stored in pgvector field)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--workers", type=int, default=5, help="Number of concurrent workers"
        )
        parser.add_argument(
            "--batch-size", type=int, default=100, help="Batch size for DB updates"
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-generate embeddings for ALL tools, not just missing ones",
        )

    def handle(self, *args, **options):
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        workers = options["workers"]
        batch_size = options["batch_size"]
        force = options["force"]

        total_tools = Tool.objects.count()
        tools_with = Tool.objects.filter(embedding__isnull=False).count()

        self.stdout.write(f"Total tools: {total_tools}")
        self.stdout.write(f"Already have embeddings: {tools_with}")

        if force:
            qs = Tool.objects.all()
        else:
            qs = Tool.objects.filter(embedding__isnull=True)

        self.stdout.write(f"Tools to process: {qs.count()}")

        if not qs.exists():
            self.stdout.write(self.style.SUCCESS("Nothing to do — all embeddings present."))
            return

        tool_data = [
            (
                tool.id,
                " ".join(
                    filter(
                        None,
                        [
                            tool.name,
                            tool.short_description or "",
                            tool.description or "",
                            " ".join(tool.tags or []),
                            " ".join(tool.use_cases or []),
                            " ".join(tool.features or []),
                            tool.startup_benefits or "",
                            " ".join(tool.ideal_for or []),
                        ],
                    )
                ),
            )
            for tool in qs
        ]

        success = 0
        failure = 0

        for i in range(0, len(tool_data), batch_size):
            batch = tool_data[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(tool_data) - 1) // batch_size + 1
            self.stdout.write(f"Batch {batch_num}/{total_batches} ({len(batch)} tools)")

            updates = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(self._generate_embedding, client, data): data
                    for data in batch
                }
                for future in as_completed(futures):
                    tool_id, embedding, error = future.result()
                    if embedding is not None:
                        updates.append(Tool(id=tool_id, embedding=embedding))
                        success += 1
                        self.stdout.write(f"  ✓ tool_id={tool_id}")
                    else:
                        failure += 1
                        self.stdout.write(
                            self.style.WARNING(f"  ✗ tool_id={tool_id}: {error}")
                        )

            if updates:
                Tool.objects.bulk_update(updates, ["embedding"])
                self.stdout.write(f"  Saved {len(updates)} embeddings.")

        self.stdout.write(
            self.style.SUCCESS(f"Done. Success: {success}, Failed: {failure}")
        )

    @staticmethod
    def _generate_embedding(client: OpenAI, tool_data: tuple):
        tool_id, text = tool_data
        try:
            # Truncate to stay within token limits (~8192 tokens for ada-002)
            text = text[:6000]
            response = client.embeddings.create(
                model="text-embedding-ada-002", input=text
            )
            embedding = response.data[0].embedding  # object attribute, not dict key
            return tool_id, embedding, None
        except Exception as e:
            return tool_id, None, str(e)
