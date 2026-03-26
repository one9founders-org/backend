"""
scraper_exception_fix_guide.py
-------------------------------
This file shows the PATTERN to apply across every scraper.
Do a find-replace of the anti-pattern in:

  - scrapers/lacreme.py            (lines 167, 177, 185, 211)
  - scrapers/huggingface/scraper.py (lines 126, 179)
  - scrapers/taaft/scraper.py       (lines 117, 284)
  - rag_directory/management/commands/sync_github.py (lines 68, 91)
  - api/models.py                   (lines 189, 379)

───────────────────────────────────────────────
ANTI-PATTERN (what you have now):
───────────────────────────────────────────────

    try:
        do_something()
    except Exception:
        pass          ← failure is swallowed silently, impossible to debug

───────────────────────────────────────────────
FIX PATTERN A — recoverable / expected errors (scrapers, enrichment):
───────────────────────────────────────────────

    import logging
    logger = logging.getLogger(__name__)

    try:
        do_something()
    except Exception as e:
        logger.warning("Short description of what failed: %s", e)

Use WARNING for things that are expected to fail sometimes (network, 3rd-party API).

───────────────────────────────────────────────
FIX PATTERN B — unexpected / data errors (models, sync):
───────────────────────────────────────────────

    try:
        do_something()
    except Exception as e:
        logger.error("Unexpected error in <context>: %s", e, exc_info=True)
        # exc_info=True attaches the full traceback to the log entry

Use ERROR + exc_info=True for things that should not fail (DB writes, sync logic).

───────────────────────────────────────────────
CONCRETE EXAMPLE — api/models.py line 379 (ToolSubmission.save):
───────────────────────────────────────────────

BEFORE:
    try:
        from .ai_enrichment import enrich_tool_data
        self.enriched_data = enrich_tool_data(self.name, self.description, self.website)
    except Exception:
        pass

AFTER:
    try:
        from .ai_enrichment import enrich_tool_data
        self.enriched_data = enrich_tool_data(self.name, self.description, self.website)
    except Exception as e:
        logger.warning(
            "AI enrichment failed for submission '%s': %s", self.name, e
        )

───────────────────────────────────────────────
CONCRETE EXAMPLE — scrapers/lacreme.py line 185:
───────────────────────────────────────────────

BEFORE:
    except Exception:
        pass

AFTER:
    except Exception as e:
        logger.warning("lacreme: failed to clear filters — continuing: %s", e)

───────────────────────────────────────────────
CONCRETE EXAMPLE — rag_directory/management/commands/sync_github.py line 68:
───────────────────────────────────────────────

BEFORE:
    except Exception:
        pass

AFTER:
    except Exception as e:
        logger.error(
            "sync_github: failed to update tool '%s': %s",
            tool.slug, e, exc_info=True
        )
        # Optionally: continue to next tool rather than crashing the whole sync

───────────────────────────────────────────────
WHY THIS MATTERS:
───────────────────────────────────────────────
  - Silent `pass` blocks are the #1 reason "it works locally but breaks in prod"
    with no traceable error.
  - Every warning/error lands in Django's log file (logs/django.log) and your
    console, making production issues immediately visible.
  - It costs zero extra effort — just replace `pass` with one logger line.
"""
