"""Spend the Claude credit on directory verification.

Writes JSONL under enrichment-logs/. Does not update the database.
Stops at --budget-usd. Safe to re-run: slugs already in the JSONL are skipped.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from django.conf import settings  # noqa: E402

if not settings.configured:
    settings.configure(
        ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY", ""),
        OPENAI_API_KEY="unused",
        HYGIENE_PROVIDER="claude",
        HYGIENE_CLAUDE_MODEL="claude-opus-5-5",
        HYGIENE_CLAUDE_EFFORT="high",
        SECRET_KEY="x",
        USE_TZ=True,
        BASE_DIR=ROOT,
    )

from api.llm import ClaudeCallError, complete_json  # noqa: E402

LOG_PATH = ROOT / "enrichment-logs" / "2026-10-16-spend-all.jsonl"
SUMMARY_PATH = ROOT / "enrichment-logs" / "2026-10-16-spend-all-summary.json"
SKIP_SLUGS = {"claude"}
PRIORITY = [
    "chatgpt",
    "notion",
    "grammarly",
    "midjourney",
    "zapier",
    "elevenlabs",
    "jasper",
    "hubspot",
    "webflow",
    "airtable",
    "framer",
    "copy-ai",
    "perplexity",
    "canva",
    "slack",
    "figma",
    "linear",
    "supabase",
    "vercel",
    "stripe",
]

SYSTEM = """You verify software products for a public directory of tools for startup founders.

Search the live web. Use the official website first, then a pricing or docs page.
Rules:
- Record only what a page you opened supports. If you cannot find it, leave the string empty, use unknown, or false, and lower confidence.
- Do not invent prices, customer names, free trials, or features.
- pricing_summary is one or two sentences with the actual tiers and numbers you found, or empty.
- pricing_source_url must be a page on the product's own domain. If the only price is on a review, comparison, or directory site, leave pricing_summary and pricing_source_url empty and mention that in notes.
- official_url is the product's own site, or empty.
- status is shutdown only when a page says the product is discontinued. acquired only when a page names the buyer. Otherwise active if the site is up, else unknown.
- short_description is 8 to 18 words, no trailing period, no slogans.
- description is 50 to 90 words, third person, plain.
- features, use_cases, and integrations are short phrases from the sources. Empty arrays are correct.
- confidence is 0 to 1 for the whole record. Use below 0.6 when the official site was not found.
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "exists",
        "official_url",
        "company",
        "status",
        "short_description",
        "description",
        "pricing_type",
        "pricing_summary",
        "pricing_source_url",
        "free_tier",
        "features",
        "use_cases",
        "integrations",
        "confidence",
        "notes",
    ],
    "properties": {
        "exists": {"type": "boolean"},
        "official_url": {"type": "string"},
        "company": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["active", "acquired", "shutdown", "unknown"],
        },
        "short_description": {"type": "string"},
        "description": {"type": "string"},
        "pricing_type": {
            "type": "string",
            "enum": ["free", "freemium", "paid", "unknown"],
        },
        "pricing_summary": {"type": "string"},
        "pricing_source_url": {"type": "string"},
        "free_tier": {"type": "boolean"},
        "features": {"type": "array", "items": {"type": "string"}},
        "use_cases": {"type": "array", "items": {"type": "string"}},
        "integrations": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "notes": {"type": "string"},
    },
}


class Budget:
    def __init__(self, cap: float, reserve: float):
        self.cap = cap
        self.reserve = reserve
        self.spent = 0.0
        self.session_spent = 0.0
        self.inflight = 0
        self.calls = 0
        self.errors = 0
        self._lock = threading.Lock()

    def try_start(self) -> bool:
        with self._lock:
            projected = self.spent + (self.inflight + 1) * self.reserve
            if projected > self.cap:
                return False
            self.inflight += 1
            return True

    def finish(self, cost: float, *, error: bool = False) -> None:
        with self._lock:
            self.spent += cost
            self.session_spent += cost
            self.inflight = max(0, self.inflight - 1)
            self.calls += 1
            if error:
                self.errors += 1
            if self.calls >= 8 and self.calls % 8 == 0:
                mean = self.session_spent / self.calls
                self.reserve = max(0.05, mean * 1.8)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "spent_usd": round(self.spent, 4),
                "inflight": self.inflight,
                "calls": self.calls,
                "errors": self.errors,
                "reserve": round(self.reserve, 4),
                "cap": self.cap,
            }


def load_rows() -> list[dict]:
    path = ROOT / "tools.csv"
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            slug = (row.get("slug") or "").strip()
            website = (row.get("website") or "").strip()
            if not slug or slug in SKIP_SLUGS or not website.startswith("http"):
                continue
            rows.append(
                {
                    "slug": slug,
                    "name": (row.get("name") or slug).strip(),
                    "website": website,
                    "short_description": (row.get("short_description") or "")[:240],
                }
            )
    return rows


def prior_progress() -> tuple[set[str], float]:
    found = set()
    spent = 0.0
    if not LOG_PATH.exists():
        return found, spent
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        slug = item.get("slug")
        if slug:
            found.add(slug)
        usage = item.get("usage") or {}
        spent += float(usage.get("cost_usd") or 0)
    return found, spent


def prompt_for(row: dict) -> str:
    return (
        f"Verify this directory row.\n"
        f"name: {row['name']}\n"
        f"listed_website: {row['website']}\n"
        f"current_blurb: {row['short_description']}\n"
        "Search the web before you answer."
    )


def write_summary(budget: Budget, pending: int) -> None:
    payload = budget.snapshot()
    payload["pending"] = pending
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2) + "\n")


def verify(row: dict) -> tuple[dict, float, str]:
    last_error = ""
    for attempt in range(4):
        try:
            data, usage = complete_json(
                system=SYSTEM,
                user=prompt_for(row),
                schema=SCHEMA,
                max_tokens=6000,
                effort="high",
                web_search=True,
                max_searches=3,
            )
            record = {
                "slug": row["slug"],
                "name": row["name"],
                "listed_website": row["website"],
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "usage": usage.as_dict(),
                "record": data,
            }
            return record, usage.cost_usd, ""
        except ClaudeCallError as exc:
            last_error = str(exc)
            cost = exc.usage.cost_usd if exc.usage is not None else 0.0
            retryable = any(
                token in last_error.lower()
                for token in ("rate", "429", "overloaded", "529", "timeout", "503")
            )
            if not retryable or attempt == 3:
                record = {
                    "slug": row["slug"],
                    "name": row["name"],
                    "listed_website": row["website"],
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "error": last_error[:400],
                    "usage": exc.usage.as_dict() if exc.usage is not None else {},
                }
                return record, cost, last_error
            time.sleep(5 * (attempt + 1))
    return (
        {
            "slug": row["slug"],
            "name": row["name"],
            "error": last_error[:400],
        },
        0.0,
        last_error,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget-usd", type=float, default=195.0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        sys.exit("ANTHROPIC_API_KEY is not set")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    finished, already_spent = prior_progress()
    rows = [row for row in load_rows() if row["slug"] not in finished]
    by_slug = {row["slug"]: row for row in rows}
    queue = [by_slug[slug] for slug in PRIORITY if slug in by_slug]
    queued = {row["slug"] for row in queue}
    queue.extend(row for row in rows if row["slug"] not in queued)
    if args.limit:
        queue = queue[: args.limit]
    budget = Budget(args.budget_usd, reserve=0.45)
    budget.spent = already_spent
    write_lock = threading.Lock()
    print(
        f"queued {len(queue)} already {len(finished)} budget ${args.budget_usd:.0f}",
        flush=True,
    )

    def run_one(row: dict) -> None:
        if not budget.try_start():
            return
        record, cost, error = verify(row)
        budget.finish(cost, error=bool(error))
        line = json.dumps(record, ensure_ascii=False)
        with write_lock:
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        snap = budget.snapshot()
        label = "fail" if error else "ok"
        detail = ""
        if error:
            secret = os.environ.get("ANTHROPIC_API_KEY", "")
            detail = " " + error.replace(secret, "[redacted]")[:160]
        print(
            f"{label} {row['slug']} ${cost:.4f} spent ${snap['spent_usd']:.2f} "
            f"calls {snap['calls']}{detail}",
            flush=True,
        )
        if snap["calls"] % 10 == 0:
            write_summary(budget, pending=0)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    pending = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in queue:
            snap = budget.snapshot()
            if (
                snap["spent_usd"] + (snap["inflight"] + 1) * snap["reserve"]
                > args.budget_usd
            ):
                break
            pending.append(pool.submit(run_one, row))
        for future in as_completed(pending):
            future.result()
    write_summary(budget, pending=max(0, len(queue) - budget.snapshot()["calls"]))
    snap = budget.snapshot()
    print(
        f"done spent ${snap['spent_usd']:.2f} calls {snap['calls']} errors {snap['errors']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
