"""Measure real Claude cost on a small directory sample. Writes nothing."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.discovery.facts import fetch_facts
from api.hygiene.enrich import enrich
from api.hygiene.linkcheck import (
    BROKEN,
    MALFORMED,
    OK,
    PARKED,
    REDIRECTED,
    UNREACHABLE,
    check_url,
)
from api.llm import SpendCapExceeded, spend_cap
from api.models import Tool
from api.tool_enrichment import write_enrichment_log
from api.verified_listings import VERIFIED_LISTINGS, protected_from_ai

DEAD = {BROKEN, MALFORMED, PARKED, UNREACHABLE}
ALIVE = {OK, REDIRECTED}


class Command(BaseCommand):
    help = (
        "Dry-run Opus enrichment on a mixed sample and record dollars per tool. "
        "Does not write tool rows. Stops at --budget-usd."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--budget-usd", type=float, default=5.0)
        parser.add_argument(
            "--effort",
            default="medium",
            choices=["low", "medium", "high", "xhigh", "max"],
        )
        parser.add_argument(
            "--smoke",
            action="store_true",
            help="One tiny Claude call to prove the key and model. Ignores --limit.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1 and not options["smoke"]:
            raise CommandError("--limit must be >= 1")
        if options["budget_usd"] <= 0:
            raise CommandError("--budget-usd must be > 0")
        if not (getattr(settings, "ANTHROPIC_API_KEY", "") or "").strip():
            raise CommandError("ANTHROPIC_API_KEY is not set")

        settings.HYGIENE_PROVIDER = "claude"
        settings.HYGIENE_CLAUDE_EFFORT = options["effort"]

        if options["smoke"]:
            self._smoke(options["budget_usd"])
            return
        self._sample(options["limit"], options["budget_usd"])

    def _smoke(self, budget: float) -> None:
        from api.llm import complete_json

        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        }
        with spend_cap(budget) as meter:
            data, usage = complete_json(
                system="Reply with the JSON object you were given a schema for.",
                user="Set ok to true.",
                schema=schema,
                max_tokens=1024,
                effort="low",
            )
        self.stdout.write(f"smoke ok={data.get('ok')} cost=${usage.cost_usd:.4f}")
        self.stdout.write(
            f"tokens in={usage.input_tokens} out={usage.output_tokens} "
            f"stop={usage.stop_reason} meter=${meter.spent_usd:.4f}"
        )

    def _sample(self, limit: int, budget: float) -> None:
        tools = _sample_tools(limit)
        if not tools:
            raise CommandError("No eligible tools. Check the database connection.")

        entries = []
        aborted = ""
        called = 0
        with spend_cap(budget) as meter:
            for tool in tools:
                if meter.exceeded():
                    aborted = f"spend ${meter.spent_usd:.4f} reached cap ${budget:.2f}"
                    break
                row = {
                    "tool_id": tool.id,
                    "name": tool.name,
                    "slug": tool.slug,
                    "website": tool.website,
                    "featured": tool.is_featured,
                    "language_review_needed": tool.language_review_needed,
                }
                link = check_url(tool.website or "")
                row["link_status"] = link.status
                if link.status in DEAD:
                    row["skipped"] = f"dead link ({link.status})"
                    entries.append(row)
                    self.stdout.write(f"skip {tool.slug}: {row['skipped']}")
                    continue
                if link.status not in ALIVE:
                    row["skipped"] = f"link {link.status}"
                    entries.append(row)
                    self.stdout.write(f"skip {tool.slug}: {row['skipped']}")
                    continue
                try:
                    facts = fetch_facts(link.final_url or tool.website)
                    enriched = enrich(tool.name, link.final_url or tool.website, facts)
                except SpendCapExceeded as exc:
                    aborted = str(exc)
                    row["error"] = aborted
                    entries.append(row)
                    break
                except Exception as exc:
                    row["error"] = str(exc)
                    entries.append(row)
                    self.stdout.write(self.style.WARNING(f"fail {tool.slug}: {exc}"))
                    continue
                usage = enriched.get("usage") or {}
                row["usage"] = usage
                row["insufficient_evidence"] = bool(
                    enriched.get("insufficient_evidence")
                )
                row["confidence"] = enriched.get("confidence")
                row["short_description"] = enriched.get("short_description", "")
                entries.append(row)
                called += 1
                cost = float(usage.get("cost_usd") or 0)
                self.stdout.write(
                    f"{tool.slug}: ${cost:.4f} "
                    f"conf={row['confidence']} "
                    f"thin={row['insufficient_evidence']}"
                )

        costs = [
            float((entry.get("usage") or {}).get("cost_usd") or 0) for entry in entries
        ]
        paid = [cost for cost in costs if cost > 0]
        payload = {
            "kind": "claude_pilot",
            "applied": False,
            "budget_usd": budget,
            "spent_usd": round(meter.spent_usd, 6),
            "model": settings.HYGIENE_CLAUDE_MODEL,
            "effort": settings.HYGIENE_CLAUDE_EFFORT,
            "called": called,
            "aborted": bool(aborted),
            "abort_reason": aborted,
            "mean_usd": round(sum(paid) / len(paid), 6) if paid else 0,
            "entries": entries,
        }
        log_path = write_enrichment_log(payload)
        self.stdout.write("--- Claude pilot (dry run, nothing written) ---")
        self.stdout.write(f"Called:  {called}")
        self.stdout.write(f"Spent:   ${meter.spent_usd:.4f} / ${budget:.2f}")
        if paid:
            self.stdout.write(f"Mean:    ${payload['mean_usd']:.4f} per called tool")
        if aborted:
            self.stdout.write(self.style.WARNING(f"Aborted: {aborted}"))
        self.stdout.write(f"Log:     {log_path}")


def _sample_tools(limit: int) -> list:
    base = (
        Tool.objects.exclude(website__isnull=True)
        .exclude(website="")
        .exclude(slug__in=list(VERIFIED_LISTINGS))
        .exclude(link_status__in=list(DEAD))
    )
    featured = [
        tool
        for tool in base.filter(is_featured=True).order_by("-views_count", "id")[:8]
        if not protected_from_ai(tool)
    ][:5]
    chosen = {tool.id for tool in featured}
    flagged = [
        tool
        for tool in base.filter(language_review_needed=True)
        .exclude(id__in=chosen)
        .order_by("id")[:6]
        if not protected_from_ai(tool)
    ][:3]
    chosen.update(tool.id for tool in flagged)
    rest_n = max(limit - len(featured) - len(flagged), 0)
    rest = [
        tool
        for tool in base.exclude(id__in=chosen).order_by("-views_count", "id")[
            : rest_n + 10
        ]
        if not protected_from_ai(tool)
    ][:rest_n]
    return (featured + flagged + rest)[:limit]
