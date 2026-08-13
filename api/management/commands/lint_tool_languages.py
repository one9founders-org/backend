from django.core.management.base import BaseCommand

from api.language import (
    description_needs_review,
    known_english_translation,
)
from api.models import Tool


class Command(BaseCommand):
    help = "Flag (and optionally fix) non-English tool descriptions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help=(
                "Apply known English translations and persist "
                "language_review_needed flags."
            ),
        )

    def handle(self, *args, **options):
        apply_fix = options["fix"]
        flagged = 0
        fixed = 0

        qs = Tool.objects.all().only(
            "id",
            "name",
            "slug",
            "description",
            "short_description",
            "language_review_needed",
        )
        for tool in qs.iterator(chunk_size=500):
            known = known_english_translation(tool.description)
            needs_review = description_needs_review(
                tool.description
            ) or description_needs_review(tool.short_description)

            if known:
                self.stdout.write(
                    f"KNOWN  {tool.slug}: {tool.description[:80]!r} -> {known!r}"
                )
                if apply_fix:
                    tool.description = known
                    tool.language_review_needed = False
                    tool.save(
                        update_fields=[
                            "description",
                            "language_review_needed",
                            "updated_at",
                        ]
                    )
                    fixed += 1
                continue

            if needs_review:
                flagged += 1
                self.stdout.write(f"FLAG   {tool.slug}: {tool.description[:120]!r}")
                if apply_fix and not tool.language_review_needed:
                    tool.language_review_needed = True
                    tool.save(update_fields=["language_review_needed", "updated_at"])

        extra = Tool.objects.filter(language_review_needed=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. flagged={flagged} known_fixed={fixed} "
                f"language_review_needed={extra} apply_fix={apply_fix}"
            )
        )
