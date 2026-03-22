import logging
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from rag_directory.models import GitHubSnapshot, RagTool

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sync GitHub stats for RAG tools with GitHub repos"

    def handle(self, *args, **options):
        token = getattr(settings, "GITHUB_TOKEN", "") or ""
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"

        tools = RagTool.objects.exclude(github_repo="").exclude(
            github_repo__isnull=True
        )
        self.stdout.write(f"Syncing GitHub stats for {tools.count()} tools...")

        updated = 0
        failed = 0
        today = timezone.now().date()
        stale_threshold = timezone.now() - timedelta(days=90)

        for tool in tools:
            try:
                repo_url = f"https://api.github.com/repos/{tool.github_repo}"
                resp = requests.get(repo_url, headers=headers, timeout=15)

                if resp.status_code != 200:
                    logger.warning(
                        "GitHub API error for %s: %s",
                        tool.github_repo,
                        resp.status_code,
                    )
                    failed += 1
                    time.sleep(0.5)
                    continue

                data = resp.json()
                stars = data.get("stargazers_count", 0)
                forks = data.get("forks_count", 0)
                open_issues = data.get("open_issues_count", 0)
                pushed_at = data.get("pushed_at")

                # Get latest release
                latest_release = ""
                try:
                    release_url = (
                        "https://api.github.com/repos/"
                        f"{tool.github_repo}/releases/latest"
                    )
                    release_resp = requests.get(
                        release_url, headers=headers, timeout=15
                    )
                    if release_resp.status_code == 200:
                        latest_release = release_resp.json().get("tag_name", "")
                except Exception:
                    pass

                # Get contributor count
                contributors = 0
                try:
                    contrib_url = (
                        f"https://api.github.com/repos/{tool.github_repo}/contributors"
                        "?per_page=1&anon=true"
                    )
                    contrib_resp = requests.get(
                        contrib_url, headers=headers, timeout=15
                    )
                    if contrib_resp.status_code == 200:
                        link_header = contrib_resp.headers.get("Link", "")
                        if 'rel="last"' in link_header:
                            import re

                            match = re.search(r"page=(\d+)>; rel=\"last\"", link_header)
                            if match:
                                contributors = int(match.group(1))
                        else:
                            contributors = len(contrib_resp.json())
                except Exception:
                    pass

                # Parse pushed_at once upfront for consistent usage
                from django.utils.dateparse import parse_datetime

                parsed_pushed_at = parse_datetime(pushed_at) if pushed_at else None

                # Create snapshot
                GitHubSnapshot.objects.update_or_create(
                    tool=tool,
                    snapshot_date=today,
                    defaults={
                        "stars": stars,
                        "forks": forks,
                        "open_issues": open_issues,
                        "contributors": contributors,
                        "last_commit_at": parsed_pushed_at,
                        "latest_release": latest_release,
                    },
                )

                # Update denormalized fields on tool
                tool.github_stars = stars
                tool.github_forks = forks
                tool.latest_release = latest_release
                tool.last_commit_at = parsed_pushed_at

                # Mark stale if no commits in 90 days, or reset to active
                # Preserve manually-set statuses like "deprecated"
                if parsed_pushed_at and parsed_pushed_at < stale_threshold:
                    if tool.status != "deprecated":
                        tool.status = "stale"
                elif parsed_pushed_at:
                    if tool.status == "stale":
                        tool.status = "active"

                tool.save(
                    update_fields=[
                        "github_stars",
                        "github_forks",
                        "last_commit_at",
                        "latest_release",
                        "status",
                    ]
                )

                updated += 1
                time.sleep(0.5)

            except Exception as e:
                logger.error("Error syncing %s: %s", tool.github_repo, e)
                failed += 1
                time.sleep(0.5)

        self.stdout.write(
            self.style.SUCCESS(f"Synced {updated} tools, {failed} failed")
        )
