import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Prevent multiple instances
lock_file = "/tmp/generate_embeddings.lock"
if os.path.exists(lock_file):
    print("Script already running! Delete /tmp/generate_embeddings.lock if stuck.")
    sys.exit(1)

# Create lock file
with open(lock_file, "w") as f:
    f.write(str(os.getpid()))

print("Starting embedding generation script...")
start_time = time.time()

try:
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    import openai
    from django.conf import settings

    from api.models import Tool

    print("All imports successful")
except Exception as e:
    print(f"Setup failed: {e}")
    sys.exit(1)

openai.api_key = settings.OPENAI_API_KEY


def build_embedding_text(tool):
    """Build rich text for embedding generation - matches Tool.save() method"""
    parts = [
        tool.name,
        tool.short_description or "",
        tool.description or "",
        " ".join(tool.tags or []),
        " ".join(tool.use_cases or []),
        " ".join(tool.features or []),
        tool.startup_benefits or "",
        " ".join(tool.ideal_for or []),
    ]
    return " ".join(filter(None, parts))


def generate_embedding(tool_data):
    tool_id, text = tool_data
    try:
        response = openai.Embedding.create(model="text-embedding-ada-002", input=text)
        return tool_id, response["data"][0]["embedding"], None
    except Exception as e:
        return tool_id, None, str(e)


def process_batch(batch_data, batch_num, total_batches):
    """Process a batch of tools"""
    batch_start = time.time()
    updates = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(generate_embedding, data): data for data in batch_data
        }

        for future in as_completed(futures):
            tool_id, embedding, error = future.result()
            if embedding:
                updates.append(Tool(id=tool_id, embedding=embedding))
                print(f"✓ Tool {tool_id}")
            else:
                print(f"✗ Tool {tool_id}: {error}")

    # Bulk update this batch
    if updates:
        Tool.objects.bulk_update(updates, ["embedding"])

    batch_time = time.time() - batch_start
    total_elapsed = time.time() - start_time

    # Progress and ETA calculation
    processed = batch_num * len(batch_data) + len(updates)
    rate = processed / total_elapsed * 60  # per minute
    remaining = total_tools_needed - processed
    eta_minutes = remaining / rate if rate > 0 else 0

    print(
        f"Batch {batch_num}/{total_batches} complete: {len(updates)} tools in {batch_time:.1f}s"
    )
    print(
        f"Progress: {processed}/{total_tools_needed} | Rate: {rate:.0f}/min | ETA: {eta_minutes:.1f}min"
    )
    print("-" * 60)


# Get tools needing embeddings
tools_without_embeddings = Tool.objects.filter(embedding__isnull=True)
total_tools = Tool.objects.count()
tools_with_embeddings = Tool.objects.filter(embedding__isnull=False).count()
total_tools_needed = tools_without_embeddings.count()

print(f"Total tools in database: {total_tools}")
print(f"Tools with embeddings: {tools_with_embeddings}")
print(f"Tools needing embeddings: {total_tools_needed}")

if total_tools_needed == 0:
    print("All tools already have embeddings!")
    sys.exit(0)

# Estimate time
estimated_minutes = total_tools_needed / 300  # Conservative rate
print(
    f"Estimated time: {estimated_minutes:.1f} minutes ({estimated_minutes/60:.1f} hours)"
)
print("=" * 60)

# Process in batches of 500 to avoid memory issues
batch_size = 500
tool_data = [
    (tool.id, build_embedding_text(tool)) for tool in tools_without_embeddings
]
total_batches = (len(tool_data) + batch_size - 1) // batch_size

for i in range(0, len(tool_data), batch_size):
    batch_num = i // batch_size + 1
    batch = tool_data[i : i + batch_size]
    process_batch(batch, batch_num, total_batches)

total_time = time.time() - start_time
print(f"\n🎉 Done! Processed {total_tools_needed} tools in {total_time/60:.1f} minutes")

# Clean up lock file
os.remove(lock_file)
