from concurrent.futures import ThreadPoolExecutor, as_completed

import openai
from django.conf import settings
from django.core.management.base import BaseCommand

from api.models import Tool


class Command(BaseCommand):
    help = "Generate embeddings for tools"

    def add_arguments(self, parser):
        parser.add_argument(
            "--workers", type=int, default=5, help="Number of concurrent workers"
        )
        parser.add_argument(
            "--batch-size", type=int, default=100, help="Batch size for processing"
        )

    def handle(self, *args, **options):
        openai.api_key = settings.OPENAI_API_KEY
        workers = options["workers"]
        batch_size = options["batch_size"]

        tools_without_embeddings = Tool.objects.filter(embedding__isnull=True)
        total_tools = Tool.objects.count()
        tools_with_embeddings = Tool.objects.filter(embedding__isnull=False).count()

        self.stdout.write(f"Total tools in database: {total_tools}")
        self.stdout.write(f"Tools with embeddings: {tools_with_embeddings}")
        self.stdout.write(
            f"Tools needing embeddings: {tools_without_embeddings.count()}"
        )

        if not tools_without_embeddings.exists():
            self.stdout.write(self.style.SUCCESS("All tools already have embeddings!"))
            return

        tool_data = [
            (tool.id, f"{tool.name} - {tool.description}")
            for tool in tools_without_embeddings
        ]

        # Process in batches
        for i in range(0, len(tool_data), batch_size):
            batch = tool_data[i : i + batch_size]
            self.stdout.write(
                f"Processing batch {i//batch_size + 1}/{(len(tool_data)-1)//batch_size + 1}"
            )

            updates = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(self.generate_embedding, data): data
                    for data in batch
                }

                for future in as_completed(futures):
                    tool_id, embedding, error = future.result()
                    if embedding:
                        updates.append(Tool(id=tool_id, embedding=embedding))
                        self.stdout.write(f"✓ Tool {tool_id}")
                    else:
                        self.stdout.write(f"✗ Tool {tool_id}: {error}")

            if updates:
                Tool.objects.bulk_update(updates, ["embedding"])
                self.stdout.write(f"Updated {len(updates)} tools in batch")

        self.stdout.write(self.style.SUCCESS("Done generating embeddings!"))

    def generate_embedding(self, tool_data):
        tool_id, text = tool_data
        try:
            response = openai.Embedding.create(
                model="text-embedding-ada-002", input=text
            )
            return tool_id, response["data"][0]["embedding"], None
        except Exception as e:
            return tool_id, None, str(e)
