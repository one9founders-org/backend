import hashlib
import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.discovery import firecrawl
from api.discovery.product_hunt_resolution import resolve_product_hunt_url
from api.models import ExternalToolCandidate


class Command(BaseCommand):
    help = (
        "Resolve missing official URLs for staged Product Hunt candidates with "
        "confidence-gated Firecrawl search. Resolved records return to pending review."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=40,
            help="Maximum unresolved candidates to search (default 40).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print high-confidence matches without updating candidates.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be >= 1")
        if not firecrawl.firecrawl_enabled():
            raise CommandError("FIRECRAWL_API_KEY is not configured")

        candidates = list(
            ExternalToolCandidate.objects.filter(
                source="producthunt",
                official_url="",
                status__in=[
                    ExternalToolCandidate.STATUS_PENDING,
                    ExternalToolCandidate.STATUS_ERROR,
                ],
            ).order_by("discovered_at")[:limit]
        )

        resolved = unresolved = 0
        for candidate in candidates:
            summary = str((candidate.payload or {}).get("summary") or "")
            match = resolve_product_hunt_url(candidate.name, summary=summary)
            if match is None:
                unresolved += 1
                self.stdout.write(f"REVIEW {candidate.name}: no unique strong match")
                continue

            resolved += 1
            self.stdout.write(
                f"MATCH {candidate.name}: {match.url} "
                f"(confidence {match.confidence:.2f})"
            )
            if options["dry_run"]:
                continue

            payload = dict(candidate.payload or {})
            payload["official_resolution"] = {
                "provider": "firecrawl_search",
                "query": match.query,
                "matched_title": match.title,
                "confidence": match.confidence,
                "reason": match.reason,
                "resolved_at": timezone.now().isoformat(),
            }
            candidate.official_url = match.url
            candidate.payload = payload
            candidate.content_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()
            candidate.status = ExternalToolCandidate.STATUS_PENDING
            candidate.review_notes = (
                "Official URL suggested by Firecrawl search. "
                "Review the domain before approval."
            )
            candidate.save(
                update_fields=[
                    "official_url",
                    "payload",
                    "content_hash",
                    "status",
                    "review_notes",
                    "updated_at",
                ]
            )

        self.stdout.write("--- Product Hunt URL resolution summary ---")
        self.stdout.write(f"searched: {len(candidates)}")
        self.stdout.write(f"resolved: {resolved}")
        self.stdout.write(f"needs_review: {unresolved}")
        if options["dry_run"]:
            self.stdout.write("dry_run: no candidates were updated")
