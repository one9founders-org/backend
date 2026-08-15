from django.core.management.base import BaseCommand

from api.discovery.sources import candidate_signal, discover_candidates


class Command(BaseCommand):
    help = (
        "Fetch GitHub / Product Hunt / HN candidates, dedupe against Tools, "
        "and print the list. Does not create records."
    )

    def handle(self, *args, **options):
        candidates = discover_candidates()
        if not candidates:
            self.stdout.write("No new candidates.")
            return

        self.stdout.write(f"Found {len(candidates)} new candidates:\n")
        for item in candidates:
            signal = candidate_signal(item)
            self.stdout.write(
                f"- {item['name']}  {item['url']}  "
                f"[{item.get('sourceType')}] signal={signal}"
            )
