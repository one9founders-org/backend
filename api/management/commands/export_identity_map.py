"""Print the tool/agent overlap map. Does not change URLs."""

import json

from django.core.management.base import BaseCommand

from api.identity import overlap_rows


class Command(BaseCommand):
    help = "Write the reviewable tool-to-agent canonical map as JSON."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        payload = {
            "redirects_applied": False,
            "preferred_family": "/agents/{slug}",
            "overlaps": overlap_rows(limit=options["limit"]),
        }
        self.stdout.write(json.dumps(payload, indent=2))
