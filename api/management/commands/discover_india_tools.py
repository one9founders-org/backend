"""Discover Indian + newly launched AI tools via Firecrawl and publish them."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.discovery import MAX_FIRECRAWL_TOOLS_PER_RUN
from api.discovery.pipeline import run_india_and_new_discovery


class Command(BaseCommand):
    help = (
        "OPT-IN Firecrawl pass for Indian + newly launched AI tools. "
        "JSON extract costs ~5 credits/page — requires "
        "FIRECRAWL_DISCOVERY_ENABLED=true and FIRECRAWL_API_KEY. "
        "Default free discovery is: manage.py run_tool_discovery"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=MAX_FIRECRAWL_TOOLS_PER_RUN,
            help=(
                f"Max new tools to publish this run "
                f"(default {MAX_FIRECRAWL_TOOLS_PER_RUN})."
            ),
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Allow this run even when FIRECRAWL_DISCOVERY_ENABLED is unset "
                "(still needs FIRECRAWL_API_KEY)."
            ),
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be >= 1")
        enabled = bool(getattr(settings, "FIRECRAWL_DISCOVERY_ENABLED", False))
        has_key = bool(getattr(settings, "FIRECRAWL_API_KEY", "") or "")
        if not has_key:
            raise CommandError("FIRECRAWL_API_KEY is not set.")
        if not enabled and not options["force"]:
            raise CommandError(
                "FIRECRAWL_DISCOVERY_ENABLED is off (default). "
                "Set it to true in the environment, or pass --force for a "
                "one-off run. Each product page costs ~5 Firecrawl credits."
            )
        if options["force"] and not enabled:
            # Temporarily enable for this process only.
            settings.FIRECRAWL_DISCOVERY_ENABLED = True
            self.stdout.write(
                self.style.WARNING(
                    "FIRECRAWL_DISCOVERY_ENABLED forced for this process only."
                )
            )
        self.stdout.write("--- Firecrawl India + new tools discovery ---")
        result = run_india_and_new_discovery(max_new=limit)
        for key, value in sorted(result.items()):
            self.stdout.write(f"  {key}: {value}")
