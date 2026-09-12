"""Bulk-catalogue open-source AI repos from GitHub (and GitLab / Codeberg).

Uses star-bin partitioning so GitHub Search's 1,000-result cap does not hide
repos. Forge candidates get attribution blurbs (no LLM) and publish with credit
to the upstream maintainers.
"""

from django.core.management.base import BaseCommand

from api.discovery.pipeline import run_new_tool_discovery


class Command(BaseCommand):
    help = (
        "Full OSS sweep: GitHub AI/LLM repos at 100+ stars (bin-split past the "
        "Search API's 1k cap), plus GitLab/Codeberg. Publishes with attribution "
        "to the original developers."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-new",
            type=int,
            default=200,
            help="Cap on new Tool rows this run (default 200).",
        )
        parser.add_argument(
            "--full-github-sweep",
            action="store_true",
            default=True,
            help="Walk every topic×star-bin partition (default on).",
        )
        parser.add_argument(
            "--incremental",
            action="store_true",
            help="Skip full GitHub sweep; use the cheaper daily query mix.",
        )

    def handle(self, *args, **options):
        max_new = options["max_new"]
        if max_new < 1:
            self.stderr.write("--max-new must be >= 1")
            return
        full_sweep = not options["incremental"]
        self.stdout.write(
            f"Starting OSS catalogue "
            f"(max_new={max_new}, full_github_sweep={full_sweep})…"
        )
        summary = run_new_tool_discovery(
            max_new=max_new,
            full_github_sweep=full_sweep,
        )
        self.stdout.write("--- OSS catalogue summary ---")
        for key in (
            "candidates_found",
            "published",
            "rejected",
            "errored",
            "deferred_over_cap",
            "staged",
            "candidate_updates",
        ):
            if key in summary:
                self.stdout.write(f"{key}: {summary[key]}")
        for source, counts in sorted(summary.get("by_source", {}).items()):
            self.stdout.write(f"  {source}: {counts}")
